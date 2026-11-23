"""The five provider reports: margin, purchasing, stock, occupancy, and cash."""

from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import UUID

from sqlmodel import SQLModel, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.commerce import PaymentReceipt, POSOrder, Quote, Reservation
from app.models.enums import MovementType, OperationStatus, PaymentMethod
from app.models.equipment import EquipmentAsset
from app.models.inventory import Ingredient, InventoryMovement, Supplier, WarehouseStock
from app.models.tenant import ServiceScheduleSlot, Tenant
from app.schemas.operations import (
    METHOD_LABELS,
    CashLine,
    EquipmentPressure,
    OccupancyCell,
    PendingBalance,
    ProfitRow,
    ProviderReports,
    PurchaseLine,
    RestockAlert,
)
from app.services.availability import slot_label
from app.services.cost_engine import as_money

_PURCHASE_WINDOW = 6
_OCCUPANCY_WINDOW = 13
_CASH_METHODS = (PaymentMethod.CASH, PaymentMethod.CARD, PaymentMethod.TRANSFER)


async def provider_reports(session: AsyncSession, tenant: Tenant) -> ProviderReports:
    today = date.today()
    reservations = await _rows(session, Reservation, tenant.id)
    quotes = {row.id: row for row in await _rows(session, Quote, tenant.id)}
    movements = await _rows(session, InventoryMovement, tenant.id)
    ingredients = {row.id: row for row in await _rows(session, Ingredient, tenant.id)}
    suppliers = {row.id: row for row in await _rows(session, Supplier, tenant.id)}
    stocks = await _rows(session, WarehouseStock, tenant.id)
    slots = {
        row.id: row for row in await _rows(session, ServiceScheduleSlot, tenant.id)
    }
    assets = {row.id: row for row in await _rows(session, EquipmentAsset, tenant.id)}
    orders = await _rows(session, POSOrder, tenant.id)
    receipts = await _rows(session, PaymentReceipt, tenant.id)
    return ProviderReports(
        profitability=_profit(reservations, quotes),
        purchases=_purchases(
            today, reservations, movements, ingredients, suppliers, stocks
        ),
        restock=_restock(ingredients, stocks),
        occupancy=_occupancy(today, tenant, reservations, slots),
        equipment=_equipment(today, reservations, quotes, assets),
        cash=_cash(orders, receipts),
        pending=_pending(today, reservations),
        generated_on=today,
    )


def _profit(
    reservations: list[Reservation], quotes: dict[UUID, Quote]
) -> list[ProfitRow]:
    rows: list[ProfitRow] = []
    for reservation in reservations:
        if reservation.operation_status is OperationStatus.CANCELLED:
            continue
        quote = quotes.get(reservation.quote_id) if reservation.quote_id else None
        food = as_money(quote.estimated_cogs) if quote is not None else Decimal("0.00")
        payload = quote.selected_extras_json if quote is not None else {}
        waiters = _stored_money(payload, "waiter_cost")
        freight = _stored_money(payload, "freight")
        revenue = as_money(reservation.total_amount)
        operating = as_money(food + waiters + freight)
        margin = as_money(revenue - operating)
        percent = (
            as_money(margin / revenue * Decimal(100)) if revenue else Decimal("0.00")
        )
        rows.append(
            ProfitRow(
                reservation_id=reservation.id,
                customer_name=reservation.customer_name,
                event_date=reservation.event_date,
                revenue=revenue,
                food_cost=food,
                waiter_cost=waiters,
                freight=freight,
                operating_cost=operating,
                margin=margin,
                margin_percent=percent,
            )
        )
    rows.sort(
        key=lambda row: (row.event_date, row.customer_name, str(row.reservation_id))
    )
    return rows


def _purchases(
    today: date,
    reservations: list[Reservation],
    movements: list[InventoryMovement],
    ingredients: dict[UUID, Ingredient],
    suppliers: dict[UUID, Supplier],
    stocks: list[WarehouseStock],
) -> list[PurchaseLine]:
    end = today + timedelta(days=_PURCHASE_WINDOW)
    upcoming = {
        row.id
        for row in reservations
        if row.operation_status in {OperationStatus.CONFIRMED, OperationStatus.IN_PREP}
        and today <= row.event_date <= end
    }
    needed: dict[UUID, float] = {}
    for movement in movements:
        if (
            movement.reference_id not in upcoming
            or movement.movement_type is not MovementType.COMMIT_RESERVE
        ):
            continue
        needed[movement.ingredient_id] = (
            needed.get(movement.ingredient_id, 0.0) + movement.quantity
        )
    available = _available_by_ingredient(stocks)
    lines: list[PurchaseLine] = []
    for ingredient_id, quantity in needed.items():
        ingredient = ingredients.get(ingredient_id)
        if ingredient is None or quantity <= 0:
            continue
        supplier = (
            suppliers.get(ingredient.supplier_id) if ingredient.supplier_id else None
        )
        on_hand = available.get(ingredient_id, 0.0)
        lines.append(
            PurchaseLine(
                supplier_name=supplier.name
                if supplier is not None
                else "Sin proveedor",
                ingredient_name=ingredient.name,
                unit=ingredient.unit.value,
                needed_qty=quantity,
                available_qty=on_hand,
                buy_qty=max(0.0, quantity - on_hand),
            )
        )
    lines.sort(key=lambda row: (row.supplier_name.lower(), row.ingredient_name.lower()))
    return lines


def _restock(
    ingredients: dict[UUID, Ingredient], stocks: list[WarehouseStock]
) -> list[RestockAlert]:
    available = _available_by_ingredient(stocks)
    alerts: list[RestockAlert] = []
    for ingredient in ingredients.values():
        on_hand = available.get(ingredient.id, 0.0)
        if on_hand <= ingredient.min_stock:
            alerts.append(
                RestockAlert(
                    ingredient_name=ingredient.name,
                    available_qty=on_hand,
                    min_stock=ingredient.min_stock,
                )
            )
    alerts.sort(key=lambda row: row.ingredient_name.lower())
    return alerts


def _occupancy(
    today: date,
    tenant: Tenant,
    reservations: list[Reservation],
    slots: dict[UUID, ServiceScheduleSlot],
) -> list[OccupancyCell]:
    end = today + timedelta(days=_OCCUPANCY_WINDOW)
    counts: dict[tuple[date, UUID], int] = {}
    for reservation in reservations:
        if reservation.operation_status is OperationStatus.CANCELLED:
            continue
        if reservation.event_date < today or reservation.event_date > end:
            continue
        key = (reservation.event_date, reservation.slot_id)
        counts[key] = counts.get(key, 0) + 1
    cells: list[OccupancyCell] = []
    for (event_date, slot_id), events in counts.items():
        slot = slots.get(slot_id)
        label = (
            slot_label(slot.start_time, slot.end_time)
            if slot is not None
            else "Horario"
        )
        cells.append(
            OccupancyCell(
                event_date=event_date,
                slot_label=label,
                events=events,
                capacity=tenant.max_concurrent_events_per_slot,
            )
        )
    cells.sort(key=lambda row: (row.event_date, row.slot_label))
    return cells


def _equipment(
    today: date,
    reservations: list[Reservation],
    quotes: dict[UUID, Quote],
    assets: dict[UUID, EquipmentAsset],
) -> list[EquipmentPressure]:
    end = today + timedelta(days=_OCCUPANCY_WINDOW)
    booked: dict[tuple[date, UUID], int] = {}
    for reservation in reservations:
        if reservation.operation_status is OperationStatus.CANCELLED:
            continue
        if reservation.event_date < today or reservation.event_date > end:
            continue
        quote = quotes.get(reservation.quote_id) if reservation.quote_id else None
        if quote is None:
            continue
        for line in _equipment_lines(quote.selected_equipment_json):
            asset_id = _asset_id(line)
            units = _units(line)
            if asset_id is None or units <= 0:
                continue
            key = (reservation.event_date, asset_id)
            booked[key] = booked.get(key, 0) + units
    pressure: list[EquipmentPressure] = []
    for (event_date, asset_id), units in booked.items():
        asset = assets.get(asset_id)
        if asset is None or units < asset.total_stock:
            continue
        pressure.append(
            EquipmentPressure(
                event_date=event_date,
                asset_name=asset.name,
                units=units,
                total_stock=asset.total_stock,
            )
        )
    pressure.sort(key=lambda row: (row.event_date, row.asset_name.lower()))
    return pressure


def _cash(orders: list[POSOrder], receipts: list[PaymentReceipt]) -> list[CashLine]:
    pos_totals = {method: Decimal("0") for method in _CASH_METHODS}
    receipt_totals = {method: Decimal("0") for method in _CASH_METHODS}
    for order in orders:
        if order.payment_method in pos_totals:
            pos_totals[order.payment_method] += order.total_amount
    for receipt in receipts:
        if receipt.is_verified and receipt.payment_method in receipt_totals:
            receipt_totals[receipt.payment_method] += receipt.amount
    return [
        CashLine(
            method_label=METHOD_LABELS[method],
            pos_total=as_money(pos_totals[method]),
            receipt_total=as_money(receipt_totals[method]),
        )
        for method in _CASH_METHODS
    ]


def _pending(today: date, reservations: list[Reservation]) -> list[PendingBalance]:
    rows: list[PendingBalance] = []
    for reservation in reservations:
        if reservation.operation_status is OperationStatus.CANCELLED:
            continue
        if reservation.event_date < today:
            continue
        balance = as_money(reservation.total_amount - reservation.paid_amount)
        if balance <= 0:
            continue
        rows.append(
            PendingBalance(
                customer_name=reservation.customer_name,
                event_date=reservation.event_date,
                balance=balance,
            )
        )
    rows.sort(key=lambda row: (row.event_date, row.customer_name))
    return rows


def _available_by_ingredient(stocks: list[WarehouseStock]) -> dict[UUID, float]:
    totals: dict[UUID, float] = {}
    for stock in stocks:
        totals[stock.ingredient_id] = (
            totals.get(stock.ingredient_id, 0.0) + stock.available_stock
        )
    return totals


def _stored_money(payload: object, key: str) -> Decimal:
    if not isinstance(payload, dict):
        return Decimal("0.00")
    raw = payload.get(key)
    if raw is None or raw == "":
        return Decimal("0.00")
    try:
        return as_money(Decimal(str(raw)))
    except InvalidOperation:
        return Decimal("0.00")


def _equipment_lines(payload: object) -> list[dict[str, object]]:
    if not isinstance(payload, dict):
        return []
    lines = payload.get("lines")
    if not isinstance(lines, list):
        return []
    return [line for line in lines if isinstance(line, dict)]


def _asset_id(line: dict[str, object]) -> UUID | None:
    raw = line.get("asset_id")
    try:
        return UUID(str(raw))
    except TypeError, ValueError:
        return None


def _units(line: dict[str, object]) -> int:
    try:
        return int(str(line.get("units", "0")))
    except ValueError:
        return 0


async def _rows[T: SQLModel](
    session: AsyncSession, model: type[T], tenant_id: UUID
) -> list[T]:
    column: Any = getattr(model, "tenant_id")  # noqa: B009
    result = await session.exec(select(model).where(column == tenant_id))
    rows = list(result.all())
    return [row for row in rows if isinstance(row, model)]
