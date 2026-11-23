"""Reservation desk: receipts, the open balance, and the inventory close."""

from decimal import Decimal
from uuid import UUID

from fastapi import HTTPException, status
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.commerce import PaymentReceipt, Reservation
from app.models.enums import MovementType, OperationStatus, PaymentMethod, PaymentStatus
from app.models.tenant import ServiceScheduleSlot, Tenant
from app.schemas.operations import (
    METHOD_LABELS,
    OPERATION_LABELS,
    PAYMENT_LABELS,
    ReceiptIn,
    ReceiptRead,
    ReservationCard,
    ReservationsScreen,
)
from app.services.availability import slot_label
from app.services.catalog_common import as_enum, clean_money, owned
from app.services.cost_engine import as_money
from app.services.inventory_service import settle_commitment

_OPEN = {OperationStatus.CONFIRMED, OperationStatus.IN_PREP}


def clean_receipt_url(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    if not cleaned:
        return None
    if len(cleaned) > 2048 or not (
        cleaned.startswith("https://") or cleaned.startswith("http://")
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="La liga del comprobante no es válida",
        )
    return cleaned


def payment_status_for(paid: Decimal, total: Decimal) -> PaymentStatus:
    if paid <= 0:
        return PaymentStatus.UNPAID
    if paid < total:
        return PaymentStatus.PARTIAL_DEPOSIT
    return PaymentStatus.PAID_IN_FULL


async def reservations_screen(
    session: AsyncSession, tenant_id: UUID
) -> ReservationsScreen:
    reservations = await _reservations(session, tenant_id)
    receipts = await _receipts(session, tenant_id)
    slots = await _slots(session, tenant_id)
    cards = [
        _card(
            row,
            slots.get(row.slot_id),
            [item for item in receipts if item.reservation_id == row.id],
        )
        for row in reservations
    ]
    cards.sort(key=lambda card: (card.event_date, card.customer_name, str(card.id)))
    return ReservationsScreen(reservations=cards)


async def add_receipt(
    session: AsyncSession,
    tenant_id: UUID,
    reservation_id: UUID,
    data: ReceiptIn,
) -> ReservationCard:
    reservation = await _reservation(session, tenant_id, reservation_id)
    amount = clean_money(data.amount, "El abono")
    if amount <= 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="El abono debe ser mayor a cero",
        )
    url = clean_receipt_url(data.receipt_file_url)
    paid = await _verified_total(session, tenant_id, reservation.id)
    if paid >= reservation.total_amount:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="La reservación ya está liquidada",
        )
    if amount > as_money(reservation.total_amount - paid):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="El abono no puede ser mayor que el saldo pendiente",
        )
    receipt = PaymentReceipt(
        tenant_id=tenant_id,
        reservation_id=reservation.id,
        amount=amount,
        payment_method=data.payment_method,
        receipt_file_url=url,
        is_verified=data.is_verified,
    )
    session.add(receipt)
    await session.flush()
    await _sync_balance(session, tenant_id, reservation)
    return await _one_card(session, tenant_id, reservation)


async def verify_receipt(
    session: AsyncSession,
    tenant_id: UUID,
    reservation_id: UUID,
    receipt_id: UUID,
) -> ReservationCard:
    reservation = await _reservation(session, tenant_id, reservation_id)
    receipt = await _receipt(session, tenant_id, reservation.id, receipt_id)
    if receipt.is_verified:
        return await _one_card(session, tenant_id, reservation)
    receipt.is_verified = True
    session.add(receipt)
    try:
        await _sync_balance(session, tenant_id, reservation)
    except HTTPException:
        receipt.is_verified = False
        session.add(receipt)
        raise
    return await _one_card(session, tenant_id, reservation)


async def delete_receipt(
    session: AsyncSession,
    tenant_id: UUID,
    reservation_id: UUID,
    receipt_id: UUID,
) -> ReservationCard:
    reservation = await _reservation(session, tenant_id, reservation_id)
    receipt = await _receipt(session, tenant_id, reservation.id, receipt_id)
    await session.delete(receipt)
    await session.flush()
    await _sync_balance(session, tenant_id, reservation)
    return await _one_card(session, tenant_id, reservation)


async def start_prep(
    session: AsyncSession, tenant_id: UUID, reservation_id: UUID
) -> ReservationCard:
    reservation = await _reservation(session, tenant_id, reservation_id)
    if reservation.operation_status is not OperationStatus.CONFIRMED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="La reservación no se puede preparar",
        )
    reservation.operation_status = OperationStatus.IN_PREP
    session.add(reservation)
    await session.flush()
    return await _one_card(session, tenant_id, reservation)


async def close_reservation(
    session: AsyncSession, tenant_id: UUID, reservation_id: UUID
) -> ReservationCard:
    reservation = await _reservation(session, tenant_id, reservation_id)
    _require_open(
        reservation,
        cancelled="La reservación está cancelada",
        closed="La reservación ya está cerrada",
    )
    await settle_commitment(
        session,
        tenant_id=tenant_id,
        reservation_id=reservation.id,
        movement_type=MovementType.PRODUCTION_OUT,
    )
    reservation.operation_status = OperationStatus.COMPLETED
    session.add(reservation)
    await session.flush()
    return await _one_card(session, tenant_id, reservation)


async def cancel_reservation(
    session: AsyncSession, tenant_id: UUID, reservation_id: UUID
) -> ReservationCard:
    reservation = await _reservation(session, tenant_id, reservation_id)
    if reservation.operation_status is OperationStatus.COMPLETED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="El evento ya se surtió",
        )
    _require_open(
        reservation,
        cancelled="La reservación ya está cancelada",
        closed="La reservación ya está cancelada",
    )
    await settle_commitment(
        session,
        tenant_id=tenant_id,
        reservation_id=reservation.id,
        movement_type=MovementType.COMMIT_RELEASE,
    )
    reservation.operation_status = OperationStatus.CANCELLED
    session.add(reservation)
    await session.flush()
    return await _one_card(session, tenant_id, reservation)


def parse_method(value: str) -> PaymentMethod:
    return as_enum(PaymentMethod, value.strip(), "El método de pago no es válido")


async def _sync_balance(
    session: AsyncSession, tenant_id: UUID, reservation: Reservation
) -> None:
    paid = await _verified_total(session, tenant_id, reservation.id)
    if paid > reservation.total_amount:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="El abono no puede ser mayor que el saldo pendiente",
        )
    reservation.paid_amount = paid
    reservation.payment_status = payment_status_for(paid, reservation.total_amount)
    session.add(reservation)
    await session.flush()


async def _verified_total(
    session: AsyncSession, tenant_id: UUID, reservation_id: UUID
) -> Decimal:
    receipts = await _receipts(session, tenant_id)
    return as_money(
        sum(
            (
                row.amount
                for row in receipts
                if row.reservation_id == reservation_id and row.is_verified
            ),
            Decimal("0"),
        )
    )


def _require_open(reservation: Reservation, *, cancelled: str, closed: str) -> None:
    if reservation.operation_status is OperationStatus.CANCELLED:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=cancelled)
    if reservation.operation_status not in _OPEN:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=closed)


async def _reservation(
    session: AsyncSession, tenant_id: UUID, reservation_id: UUID
) -> Reservation:
    return await owned(
        session,
        Reservation,
        reservation_id,
        tenant_id,
        "No se encontró la reservación",
    )


async def _receipt(
    session: AsyncSession,
    tenant_id: UUID,
    reservation_id: UUID,
    receipt_id: UUID,
) -> PaymentReceipt:
    receipt = await owned(
        session,
        PaymentReceipt,
        receipt_id,
        tenant_id,
        "No se encontró el comprobante",
    )
    if receipt.reservation_id != reservation_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No se encontró el comprobante",
        )
    return receipt


async def _one_card(
    session: AsyncSession, tenant_id: UUID, reservation: Reservation
) -> ReservationCard:
    receipts = await _receipts(session, tenant_id)
    slots = await _slots(session, tenant_id)
    return _card(
        reservation,
        slots.get(reservation.slot_id),
        [item for item in receipts if item.reservation_id == reservation.id],
    )


def _card(
    reservation: Reservation,
    slot: ServiceScheduleSlot | None,
    receipts: list[PaymentReceipt],
) -> ReservationCard:
    paid = as_money(reservation.paid_amount)
    total = as_money(reservation.total_amount)
    balance = as_money(total - paid) if paid < total else Decimal("0.00")
    label = "Horario"
    if slot is not None:
        label = slot_label(slot.start_time, slot.end_time)
    ordered = sorted(receipts, key=lambda row: (row.uploaded_at, str(row.id)))
    return ReservationCard(
        id=reservation.id,
        customer_name=reservation.customer_name,
        customer_phone=reservation.customer_phone,
        venue_address=reservation.venue_address,
        event_date=reservation.event_date,
        slot_label=label,
        guest_count=reservation.guest_count,
        total_amount=total,
        paid_amount=paid,
        balance=balance,
        payment_status=reservation.payment_status,
        payment_label=PAYMENT_LABELS[reservation.payment_status],
        operation_status=reservation.operation_status,
        operation_label=OPERATION_LABELS[reservation.operation_status],
        special_requests=reservation.special_requests,
        receipts=[
            ReceiptRead(
                id=row.id,
                amount=as_money(row.amount),
                payment_method=row.payment_method,
                method_label=METHOD_LABELS[row.payment_method],
                receipt_file_url=row.receipt_file_url,
                is_verified=row.is_verified,
            )
            for row in ordered
        ],
    )


async def _reservations(session: AsyncSession, tenant_id: UUID) -> list[Reservation]:
    result = await session.exec(
        select(Reservation).where(Reservation.tenant_id == tenant_id)
    )
    return list(result.all())


async def _receipts(session: AsyncSession, tenant_id: UUID) -> list[PaymentReceipt]:
    result = await session.exec(
        select(PaymentReceipt).where(PaymentReceipt.tenant_id == tenant_id)
    )
    return list(result.all())


async def _slots(
    session: AsyncSession, tenant_id: UUID
) -> dict[UUID, ServiceScheduleSlot]:
    result = await session.exec(
        select(ServiceScheduleSlot).where(ServiceScheduleSlot.tenant_id == tenant_id)
    )
    return {row.id: row for row in result.all()}


def tenant_tax_rate(tenant: Tenant) -> Decimal:
    return Decimal(str(tenant.default_tax_rate))
