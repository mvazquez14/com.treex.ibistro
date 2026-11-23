"""Counter sales: cash, card, or transfer, taken from physical stock."""

from decimal import Decimal, InvalidOperation
from uuid import UUID

from fastapi import HTTPException, status
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.commerce import POSOrder, Reservation
from app.models.enums import OperationStatus, PricingType
from app.models.inventory import Ingredient, Warehouse
from app.models.tenant import Tenant
from app.schemas.catalog import QuoteIn
from app.schemas.operations import (
    METHOD_LABELS,
    PosLineIn,
    PosLineRead,
    PosOrderRead,
    PosProduct,
    PosReservationOption,
    PosSaleIn,
    PosScreen,
    PosWarehouse,
)
from app.services.catalog_common import owned
from app.services.cost_engine import CostError, as_money, gross_quantity
from app.services.inventory_service import sell_physical
from app.services.menu_catalog import (
    explosion_for_recipe,
    list_extras,
    list_packages,
    quote_for_package,
)
from app.services.quoting import clean_rate, quote_totals
from app.services.reservations import tenant_tax_rate
from app.services.warehouse_catalog import list_warehouses

_KINDS = {"ingredient", "extra", "package"}


async def pos_screen(session: AsyncSession, tenant: Tenant) -> PosScreen:
    warehouses = await list_warehouses(session, tenant.id)
    products = await _catalog(session, tenant.id)
    options = await _open_reservations(session, tenant.id)
    orders = await _orders(session, tenant.id)
    return PosScreen(
        tax_rate=tenant_tax_rate(tenant),
        warehouses=[
            PosWarehouse(id=row.id, name=row.name, is_primary=row.is_primary)
            for row in warehouses
        ],
        products=products,
        reservations=options,
        orders=[_order_read(row) for row in orders],
    )


async def checkout(
    session: AsyncSession, tenant: Tenant, data: PosSaleIn
) -> PosOrderRead:
    if not data.lines:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Agrega al menos un producto",
        )
    reservation_id = await _reservation(session, tenant.id, data.reservation_id)
    warehouse = await session.get(Warehouse, data.warehouse_id)
    if warehouse is None or warehouse.tenant_id != tenant.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No se encontró el almacén",
        )
    ingredients = await _ingredients(session, tenant.id)
    priced: list[PosLineRead] = []
    needs: dict[UUID, float] = {}
    for line in data.lines:
        read, stock = await _price_line(session, tenant.id, ingredients, line)
        priced.append(read)
        for ingredient_id, quantity in stock.items():
            needs[ingredient_id] = needs.get(ingredient_id, 0.0) + quantity
    subtotal = as_money(sum((row.amount for row in priced), Decimal("0")))
    rate = clean_rate(
        data.tax_rate if data.tax_rate is not None else tenant_tax_rate(tenant)
    )
    _discount, tax, total = quote_totals(subtotal, Decimal("0"), rate, data.apply_tax)
    order = POSOrder(
        tenant_id=tenant.id,
        warehouse_id=warehouse.id,
        reservation_id=reservation_id,
        items_json={
            "lines": [
                {
                    "kind": row.kind,
                    "item_id": str(row.item_id),
                    "name": row.name,
                    "quantity": row.quantity,
                    "amount": f"{row.amount:.2f}",
                }
                for row in priced
            ]
        },
        subtotal=subtotal,
        tax_amount=tax,
        total_amount=total,
        payment_method=data.payment_method,
    )
    session.add(order)
    await session.flush()
    try:
        await sell_physical(
            session,
            tenant_id=tenant.id,
            warehouse_id=warehouse.id,
            quantities=needs,
            reference_id=order.id,
        )
    except HTTPException:
        # MemorySession.rollback is a no-op, so drop the ticket explicitly.
        await session.delete(order)
        raise
    return _order_read(order)


async def _catalog(session: AsyncSession, tenant_id: UUID) -> list[PosProduct]:
    products: list[PosProduct] = []
    for row in (await _ingredients(session, tenant_id)).values():
        if row.sale_price is None or row.sale_price <= 0:
            continue
        products.append(
            PosProduct(
                kind="ingredient",
                id=row.id,
                name=row.name,
                detail=row.unit.value,
                unit_price=as_money(row.sale_price),
            )
        )
    for extra in await list_extras(session, tenant_id):
        if not extra.is_active:
            continue
        detail = (
            "por invitado"
            if extra.pricing_type is PricingType.PER_GUEST
            else "por pieza"
        )
        products.append(
            PosProduct(
                kind="extra",
                id=extra.id,
                name=extra.name,
                detail=detail,
                unit_price=as_money(extra.unit_price),
            )
        )
    for package in await list_packages(session, tenant_id):
        if not package.is_active or any(not group.is_fixed for group in package.groups):
            continue
        products.append(
            PosProduct(
                kind="package",
                id=package.id,
                name=package.name,
                detail="por invitado",
                unit_price=as_money(package.base_price_per_guest),
            )
        )
    products.sort(key=lambda row: (row.name.lower(), row.kind, str(row.id)))
    return products


async def _price_line(
    session: AsyncSession,
    tenant_id: UUID,
    ingredients: dict[UUID, Ingredient],
    line: PosLineIn,
) -> tuple[PosLineRead, dict[UUID, float]]:
    if line.kind == "ingredient":
        return _price_ingredient(ingredients, line)
    if line.kind == "extra":
        return await _price_extra(session, tenant_id, ingredients, line)
    if line.kind == "package":
        return await _price_package(session, tenant_id, line)
    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        detail="El producto no es válido",
    )


def _price_ingredient(
    ingredients: dict[UUID, Ingredient], line: PosLineIn
) -> tuple[PosLineRead, dict[UUID, float]]:
    row = ingredients.get(line.item_id)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No se encontró el producto",
        )
    if row.sale_price is None or row.sale_price <= 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="El producto no tiene precio de venta",
        )
    amount = as_money(row.sale_price * Decimal(str(line.quantity)))
    return _read(line, row.name, amount), {row.id: line.quantity}


async def _price_extra(
    session: AsyncSession,
    tenant_id: UUID,
    ingredients: dict[UUID, Ingredient],
    line: PosLineIn,
) -> tuple[PosLineRead, dict[UUID, float]]:
    chosen = next(
        (
            row
            for row in await list_extras(session, tenant_id)
            if row.id == line.item_id
        ),
        None,
    )
    if chosen is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No se encontró el producto",
        )
    if not chosen.is_active:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="El producto no está disponible",
        )
    if chosen.pricing_type not in {PricingType.PER_GUEST, PricingType.PER_UNIT}:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="El tipo de cobro del extra no es válido",
        )
    if chosen.ingredient_id is not None and chosen.recipe_id is not None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="El extra no puede tener insumo y receta a la vez",
        )
    amount = as_money(chosen.unit_price * Decimal(str(line.quantity)))
    stock: dict[UUID, float] = {}
    if chosen.ingredient_id is not None:
        ingredient = ingredients.get(chosen.ingredient_id)
        if ingredient is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="No se encontró el insumo",
            )
        try:
            stock[ingredient.id] = gross_quantity(
                line.quantity,
                ingredient.waste_factor,
                ingredient.cooking_yield_factor,
            )
        except CostError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=str(exc),
            )
    elif chosen.recipe_id is not None:
        for need in await explosion_for_recipe(
            session, tenant_id, chosen.recipe_id, line.quantity
        ):
            if need.gross_qty > 0:
                stock[need.ingredient_id] = (
                    stock.get(need.ingredient_id, 0.0) + need.gross_qty
                )
    return _read(line, chosen.name, amount), stock


async def _price_package(
    session: AsyncSession, tenant_id: UUID, line: PosLineIn
) -> tuple[PosLineRead, dict[UUID, float]]:
    chosen = next(
        (
            row
            for row in await list_packages(session, tenant_id)
            if row.id == line.item_id
        ),
        None,
    )
    if chosen is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No se encontró el producto",
        )
    if not chosen.is_active:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="El producto no está disponible",
        )
    if abs(line.quantity - round(line.quantity)) > 1e-6:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Los paquetes se venden por invitado entero",
        )
    covers = int(round(line.quantity))
    if covers < chosen.min_guests:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"El paquete pide al menos {chosen.min_guests} invitados",
        )
    quoted = await quote_for_package(
        session,
        tenant_id,
        chosen.id,
        QuoteIn(guest_count=covers),
    )
    stock: dict[UUID, float] = {}
    for need in quoted.explosion:
        if need.gross_qty > 0:
            stock[need.ingredient_id] = (
                stock.get(need.ingredient_id, 0.0) + need.gross_qty
            )
    return _read(line, chosen.name, quoted.price), stock


def _read(line: PosLineIn, name: str, amount: Decimal) -> PosLineRead:
    return PosLineRead(
        kind=line.kind,
        item_id=line.item_id,
        name=name,
        quantity=format(Decimal(str(line.quantity)), "f"),
        amount=amount,
    )


async def _reservation(
    session: AsyncSession, tenant_id: UUID, reservation_id: UUID | None
) -> UUID | None:
    if reservation_id is None:
        return None
    reservation = await owned(
        session,
        Reservation,
        reservation_id,
        tenant_id,
        "No se encontró la reservación",
    )
    if reservation.operation_status is OperationStatus.CANCELLED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="La reservación está cancelada",
        )
    return reservation.id


async def _open_reservations(
    session: AsyncSession, tenant_id: UUID
) -> list[PosReservationOption]:
    result = await session.exec(
        select(Reservation).where(Reservation.tenant_id == tenant_id)
    )
    rows = [
        row
        for row in result.all()
        if row.operation_status is not OperationStatus.CANCELLED
    ]
    rows.sort(key=lambda row: (row.event_date, row.customer_name, str(row.id)))
    return [
        PosReservationOption(
            id=row.id,
            label=f"{row.customer_name} · {row.event_date.isoformat()}",
        )
        for row in rows
    ]


async def _ingredients(
    session: AsyncSession, tenant_id: UUID
) -> dict[UUID, Ingredient]:
    result = await session.exec(
        select(Ingredient).where(Ingredient.tenant_id == tenant_id)
    )
    return {row.id: row for row in result.all()}


async def _orders(session: AsyncSession, tenant_id: UUID) -> list[POSOrder]:
    result = await session.exec(select(POSOrder).where(POSOrder.tenant_id == tenant_id))
    rows = list(result.all())
    rows.sort(key=lambda row: (row.created_at, str(row.id)), reverse=True)
    return rows


def _order_read(order: POSOrder) -> PosOrderRead:
    payload = order.items_json.get("lines")
    lines: list[PosLineRead] = []
    if isinstance(payload, list):
        for item in payload:
            parsed = _stored_line(item)
            if parsed is not None:
                lines.append(parsed)
    return PosOrderRead(
        id=order.id,
        warehouse_id=order.warehouse_id,
        reservation_id=order.reservation_id,
        payment_method=order.payment_method,
        method_label=METHOD_LABELS[order.payment_method],
        subtotal=as_money(order.subtotal),
        tax_amount=as_money(order.tax_amount),
        total_amount=as_money(order.total_amount),
        lines=lines,
    )


def _stored_line(item: object) -> PosLineRead | None:
    if not isinstance(item, dict):
        return None
    kind = item.get("kind")
    if kind not in _KINDS:
        return None
    try:
        item_id = UUID(str(item.get("item_id")))
        amount = as_money(Decimal(str(item.get("amount", "0"))))
    except ValueError, InvalidOperation:
        return None
    name = item.get("name")
    quantity = item.get("quantity")
    return PosLineRead(
        kind=str(kind),
        item_id=item_id,
        name=name if isinstance(name, str) and name else "Producto",
        quantity=quantity if isinstance(quantity, str) and quantity else "0",
        amount=amount,
    )
