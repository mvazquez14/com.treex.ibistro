"""Dual stock and the inventory Kardex.

physical_stock is what is on the shelf. committed_stock is reserved for events.
available_stock is physical minus committed. A movement that would make the
physical stock negative is rejected.
"""

from collections.abc import Mapping
from uuid import UUID

from fastapi import HTTPException, status
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.enums import MovementType
from app.models.inventory import (
    Ingredient,
    InventoryMovement,
    Warehouse,
    WarehouseStock,
)
from app.services.cost_engine import IngredientNeed

_QTY = 1e-9


async def apply_movement(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    warehouse_id: UUID,
    ingredient_id: UUID,
    movement_type: MovementType,
    quantity: float,
    reference_id: UUID | None = None,
) -> InventoryMovement:
    await _owned_warehouse(session, tenant_id, warehouse_id)
    await _owned_ingredient(session, tenant_id, ingredient_id)
    stock = await _stock(session, tenant_id, warehouse_id, ingredient_id)
    physical, committed = _next_levels(
        physical=stock.physical_stock,
        committed=stock.committed_stock,
        movement_type=movement_type,
        quantity=quantity,
    )
    stock.physical_stock = physical
    stock.committed_stock = committed
    session.add(stock)
    movement = InventoryMovement(
        tenant_id=tenant_id,
        warehouse_id=warehouse_id,
        ingredient_id=ingredient_id,
        movement_type=movement_type,
        quantity=quantity,
        reference_id=reference_id,
    )
    session.add(movement)
    await session.flush()
    return movement


async def commit_recipe_explosion(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    lines: tuple[IngredientNeed, ...] | list[IngredientNeed],
    reference_id: UUID | None = None,
) -> list[InventoryMovement]:
    """Reserve the gross quantities of an explosion in the tenant's primary warehouse."""
    warehouse = await _primary_warehouse(session, tenant_id)
    positive = [line for line in lines if line.gross_qty > 0]
    for line in positive:
        await _owned_ingredient(session, tenant_id, line.ingredient_id)
        stock = await _find_stock(session, tenant_id, warehouse.id, line.ingredient_id)
        available = 0.0 if stock is None else stock.available_stock
        if available + _QTY < line.gross_qty:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="No hay existencia disponible para reservar",
            )
    movements: list[InventoryMovement] = []
    for line in positive:
        movements.append(
            await apply_movement(
                session,
                tenant_id=tenant_id,
                warehouse_id=warehouse.id,
                ingredient_id=line.ingredient_id,
                movement_type=MovementType.COMMIT_RESERVE,
                quantity=line.gross_qty,
                reference_id=reference_id,
            )
        )
    return movements


async def list_kardex(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    warehouse_id: UUID | None = None,
    ingredient_id: UUID | None = None,
) -> list[InventoryMovement]:
    if warehouse_id is not None:
        await _owned_warehouse(session, tenant_id, warehouse_id)
    if ingredient_id is not None:
        await _owned_ingredient(session, tenant_id, ingredient_id)
    statement = select(InventoryMovement).where(
        InventoryMovement.tenant_id == tenant_id
    )
    if warehouse_id is not None:
        statement = statement.where(InventoryMovement.warehouse_id == warehouse_id)
    if ingredient_id is not None:
        statement = statement.where(InventoryMovement.ingredient_id == ingredient_id)
    result = await session.exec(statement)
    rows = list(result.all())
    rows.sort(key=lambda row: (row.created_at, str(row.id)), reverse=True)
    return rows


async def sell_physical(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    warehouse_id: UUID,
    quantities: Mapping[UUID, float],
    reference_id: UUID | None = None,
) -> list[InventoryMovement]:
    """Take products off the shelf. Committed stock stays reserved for events."""
    await _owned_warehouse(session, tenant_id, warehouse_id)
    positive = {
        ingredient_id: quantity
        for ingredient_id, quantity in quantities.items()
        if quantity > _QTY
    }
    for ingredient_id, quantity in positive.items():
        await _owned_ingredient(session, tenant_id, ingredient_id)
        stock = await _find_stock(session, tenant_id, warehouse_id, ingredient_id)
        available = 0.0 if stock is None else stock.available_stock
        if available + _QTY < quantity:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="No hay existencia disponible para la venta",
            )
        _next_levels(
            physical=0.0 if stock is None else stock.physical_stock,
            committed=0.0 if stock is None else stock.committed_stock,
            movement_type=MovementType.POS_SALE_OUT,
            quantity=quantity,
        )
    movements: list[InventoryMovement] = []
    for ingredient_id, quantity in positive.items():
        movements.append(
            await apply_movement(
                session,
                tenant_id=tenant_id,
                warehouse_id=warehouse_id,
                ingredient_id=ingredient_id,
                movement_type=MovementType.POS_SALE_OUT,
                quantity=quantity,
                reference_id=reference_id,
            )
        )
    return movements


async def settle_commitment(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    reservation_id: UUID,
    movement_type: MovementType,
) -> list[InventoryMovement]:
    """Turn a reservation's reserves into production, or release them."""
    if movement_type not in {MovementType.PRODUCTION_OUT, MovementType.COMMIT_RELEASE}:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="El tipo de movimiento no es válido",
        )
    result = await session.exec(
        select(InventoryMovement).where(InventoryMovement.tenant_id == tenant_id)
    )
    merged: dict[tuple[UUID, UUID], float] = {}
    for row in result.all():
        if (
            row.reference_id != reservation_id
            or row.movement_type is not MovementType.COMMIT_RESERVE
        ):
            continue
        key = (row.warehouse_id, row.ingredient_id)
        merged[key] = merged.get(key, 0.0) + row.quantity
    for (warehouse_id, ingredient_id), quantity in merged.items():
        await _owned_warehouse(session, tenant_id, warehouse_id)
        await _owned_ingredient(session, tenant_id, ingredient_id)
        stock = await _find_stock(session, tenant_id, warehouse_id, ingredient_id)
        _next_levels(
            physical=0.0 if stock is None else stock.physical_stock,
            committed=0.0 if stock is None else stock.committed_stock,
            movement_type=movement_type,
            quantity=quantity,
        )
    movements: list[InventoryMovement] = []
    for (warehouse_id, ingredient_id), quantity in merged.items():
        movements.append(
            await apply_movement(
                session,
                tenant_id=tenant_id,
                warehouse_id=warehouse_id,
                ingredient_id=ingredient_id,
                movement_type=movement_type,
                quantity=quantity,
                reference_id=reservation_id,
            )
        )
    return movements


async def _primary_warehouse(session: AsyncSession, tenant_id: UUID) -> Warehouse:
    result = await session.exec(
        select(Warehouse).where(Warehouse.tenant_id == tenant_id)
    )
    rows = [row for row in result.all() if row.is_primary]
    rows.sort(key=lambda row: row.name.lower())
    if not rows:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Configura un almacén primario antes de reservar",
        )
    return rows[0]


async def _owned_warehouse(
    session: AsyncSession, tenant_id: UUID, warehouse_id: UUID
) -> Warehouse:
    row = await session.get(Warehouse, warehouse_id)
    if row is None or row.tenant_id != tenant_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No se encontró el almacén",
        )
    return row


async def _owned_ingredient(
    session: AsyncSession, tenant_id: UUID, ingredient_id: UUID
) -> Ingredient:
    row = await session.get(Ingredient, ingredient_id)
    if row is None or row.tenant_id != tenant_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No se encontró el insumo",
        )
    return row


async def _stock(
    session: AsyncSession,
    tenant_id: UUID,
    warehouse_id: UUID,
    ingredient_id: UUID,
) -> WarehouseStock:
    found = await _find_stock(session, tenant_id, warehouse_id, ingredient_id)
    if found is not None:
        return found
    return WarehouseStock(
        tenant_id=tenant_id,
        warehouse_id=warehouse_id,
        ingredient_id=ingredient_id,
        physical_stock=0,
        committed_stock=0,
    )


async def _find_stock(
    session: AsyncSession,
    tenant_id: UUID,
    warehouse_id: UUID,
    ingredient_id: UUID,
) -> WarehouseStock | None:
    result = await session.exec(
        select(WarehouseStock).where(
            WarehouseStock.tenant_id == tenant_id,
            WarehouseStock.warehouse_id == warehouse_id,
            WarehouseStock.ingredient_id == ingredient_id,
        )
    )
    return result.first()


def _next_levels(
    *,
    physical: float,
    committed: float,
    movement_type: MovementType,
    quantity: float,
) -> tuple[float, float]:
    if movement_type is MovementType.PURCHASE_IN:
        _require_positive(quantity)
        physical += quantity
    elif movement_type is MovementType.ADJUSTMENT:
        if abs(quantity) <= _QTY:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="El ajuste no puede ser cero",
            )
        physical += quantity
    elif movement_type is MovementType.COMMIT_RESERVE:
        _require_positive(quantity)
        if physical - committed + _QTY < quantity:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="No hay existencia disponible para reservar",
            )
        committed += quantity
    elif movement_type is MovementType.COMMIT_RELEASE:
        _require_positive(quantity)
        committed = max(0.0, committed - quantity)
    elif movement_type is MovementType.PRODUCTION_OUT:
        _require_positive(quantity)
        if committed + _QTY < quantity:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="El stock comprometido no alcanza para la producción",
            )
        physical -= quantity
        committed -= quantity
    elif movement_type is MovementType.POS_SALE_OUT:
        _require_positive(quantity)
        physical -= quantity
    else:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="El tipo de movimiento no es válido",
        )
    if physical < -_QTY:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="La existencia física no puede quedar en negativo",
        )
    if physical < 0:
        physical = 0
    if committed < 0:
        committed = 0
    return physical, committed


def _require_positive(quantity: float) -> None:
    if quantity <= _QTY:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="La cantidad debe ser mayor a cero",
        )
