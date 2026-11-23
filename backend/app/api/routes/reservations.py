"""JSON for the reservation desk."""

from uuid import UUID

from fastapi import APIRouter

from app.api.deps import CurrentActiveTenant, SessionDep
from app.schemas.operations import ReceiptIn, ReservationCard, ReservationsScreen
from app.services import reservations

router = APIRouter(prefix="/reservations", tags=["reservations"])


@router.get("", response_model=ReservationsScreen)
async def list_reservations(
    session: SessionDep, tenant: CurrentActiveTenant
) -> ReservationsScreen:
    return await reservations.reservations_screen(session, tenant.id)


@router.post("/{reservation_id}/receipts", response_model=ReservationCard)
async def create_receipt(
    session: SessionDep,
    tenant: CurrentActiveTenant,
    reservation_id: UUID,
    data: ReceiptIn,
) -> ReservationCard:
    card = await reservations.add_receipt(session, tenant.id, reservation_id, data)
    await session.commit()
    return card


@router.post(
    "/{reservation_id}/receipts/{receipt_id}/verify",
    response_model=ReservationCard,
)
async def verify_receipt(
    session: SessionDep,
    tenant: CurrentActiveTenant,
    reservation_id: UUID,
    receipt_id: UUID,
) -> ReservationCard:
    card = await reservations.verify_receipt(
        session, tenant.id, reservation_id, receipt_id
    )
    await session.commit()
    return card


@router.delete(
    "/{reservation_id}/receipts/{receipt_id}",
    response_model=ReservationCard,
)
async def delete_receipt(
    session: SessionDep,
    tenant: CurrentActiveTenant,
    reservation_id: UUID,
    receipt_id: UUID,
) -> ReservationCard:
    card = await reservations.delete_receipt(
        session, tenant.id, reservation_id, receipt_id
    )
    await session.commit()
    return card


@router.post("/{reservation_id}/prepare", response_model=ReservationCard)
async def prepare_reservation(
    session: SessionDep, tenant: CurrentActiveTenant, reservation_id: UUID
) -> ReservationCard:
    card = await reservations.start_prep(session, tenant.id, reservation_id)
    await session.commit()
    return card


@router.post("/{reservation_id}/close", response_model=ReservationCard)
async def close_reservation(
    session: SessionDep, tenant: CurrentActiveTenant, reservation_id: UUID
) -> ReservationCard:
    card = await reservations.close_reservation(session, tenant.id, reservation_id)
    await session.commit()
    return card


@router.post("/{reservation_id}/cancel", response_model=ReservationCard)
async def cancel_reservation(
    session: SessionDep, tenant: CurrentActiveTenant, reservation_id: UUID
) -> ReservationCard:
    card = await reservations.cancel_reservation(session, tenant.id, reservation_id)
    await session.commit()
    return card
