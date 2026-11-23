"""Suppliers, warehouses, ingredients, stock, and the Kardex for one tenant."""

from decimal import Decimal
from uuid import UUID

from fastapi import HTTPException, status
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.enums import IngredientUnit, MovementType
from app.models.inventory import (
    Ingredient,
    InventoryMovement,
    Supplier,
    Warehouse,
    WarehouseStock,
)
from app.models.menu import MenuExtra, RecipeItem
from app.schemas.catalog import (
    IngredientIn,
    IngredientRead,
    IngredientUpdate,
    MovementIn,
    MovementRead,
    StockRead,
    SupplierIn,
    SupplierRead,
    SupplierUpdate,
    WarehouseIn,
    WarehouseRead,
    WarehouseScreen,
    WarehouseUpdate,
)
from app.services.catalog_common import (
    as_enum,
    clean_email,
    clean_money,
    clean_name,
    clean_optional,
    clean_phone,
    clean_text,
    conflict,
    owned,
)
from app.services.inventory_service import apply_movement, list_kardex


async def warehouse_snapshot(
    session: AsyncSession,
    tenant_id: UUID,
    *,
    warehouse_id: UUID | None = None,
    ingredient_id: UUID | None = None,
) -> WarehouseScreen:
    return WarehouseScreen(
        suppliers=await list_suppliers(session, tenant_id),
        warehouses=await list_warehouses(session, tenant_id),
        ingredients=await list_ingredients(session, tenant_id),
        stock=await list_stock(session, tenant_id, warehouse_id=warehouse_id),
        kardex=await list_movements(
            session,
            tenant_id,
            warehouse_id=warehouse_id,
            ingredient_id=ingredient_id,
        ),
    )


async def list_suppliers(session: AsyncSession, tenant_id: UUID) -> list[SupplierRead]:
    rows = await _suppliers(session, tenant_id)
    return [
        SupplierRead(
            id=row.id,
            name=row.name,
            contact_name=row.contact_name,
            phone=row.phone,
            email=row.email,
            notes=row.notes,
        )
        for row in rows
    ]


async def create_supplier(
    session: AsyncSession, tenant_id: UUID, data: SupplierIn
) -> SupplierRead:
    row = Supplier(
        tenant_id=tenant_id,
        name=clean_name(data.name),
        contact_name=clean_text(data.contact_name, limit=255),
        phone=clean_phone(data.phone),
        email=clean_email(data.email),
        notes=clean_optional(data.notes, limit=4000),
    )
    session.add(row)
    await session.flush()
    return _supplier_read(row)


async def update_supplier(
    session: AsyncSession,
    tenant_id: UUID,
    supplier_id: UUID,
    data: SupplierUpdate,
) -> SupplierRead:
    row = await owned(
        session, Supplier, supplier_id, tenant_id, "No se encontró el proveedor"
    )
    fields = data.model_fields_set
    if "name" in fields and data.name is not None:
        row.name = clean_name(data.name)
    if "contact_name" in fields and data.contact_name is not None:
        row.contact_name = clean_text(data.contact_name, limit=255)
    if "phone" in fields and data.phone is not None:
        row.phone = clean_phone(data.phone)
    if "email" in fields:
        row.email = clean_email(data.email)
    if "notes" in fields:
        row.notes = clean_optional(data.notes, limit=4000)
    session.add(row)
    await session.flush()
    return _supplier_read(row)


async def delete_supplier(
    session: AsyncSession, tenant_id: UUID, supplier_id: UUID
) -> None:
    row = await owned(
        session, Supplier, supplier_id, tenant_id, "No se encontró el proveedor"
    )
    result = await session.exec(
        select(Ingredient).where(
            Ingredient.tenant_id == tenant_id,
            Ingredient.supplier_id == supplier_id,
        )
    )
    if list(result.all()):
        raise conflict("No se puede eliminar el proveedor porque todavía tiene insumos")
    await session.delete(row)


async def list_warehouses(
    session: AsyncSession, tenant_id: UUID
) -> list[WarehouseRead]:
    rows = await _warehouses(session, tenant_id)
    return [
        WarehouseRead(
            id=row.id,
            name=row.name,
            is_primary=row.is_primary,
            location_notes=row.location_notes,
        )
        for row in rows
    ]


async def create_warehouse(
    session: AsyncSession, tenant_id: UUID, data: WarehouseIn
) -> WarehouseRead:
    row = Warehouse(
        tenant_id=tenant_id,
        name=clean_name(data.name),
        is_primary=data.is_primary,
        location_notes=clean_optional(data.location_notes, limit=500),
    )
    session.add(row)
    await session.flush()
    if row.is_primary:
        await _keep_one_primary(session, tenant_id, row.id)
    return _warehouse_read(row)


async def update_warehouse(
    session: AsyncSession,
    tenant_id: UUID,
    warehouse_id: UUID,
    data: WarehouseUpdate,
) -> WarehouseRead:
    row = await owned(
        session, Warehouse, warehouse_id, tenant_id, "No se encontró el almacén"
    )
    fields = data.model_fields_set
    if "name" in fields and data.name is not None:
        row.name = clean_name(data.name)
    if "location_notes" in fields:
        row.location_notes = clean_optional(data.location_notes, limit=500)
    if "is_primary" in fields and data.is_primary is not None:
        row.is_primary = data.is_primary
    session.add(row)
    await session.flush()
    if row.is_primary:
        await _keep_one_primary(session, tenant_id, row.id)
    return _warehouse_read(row)


async def delete_warehouse(
    session: AsyncSession, tenant_id: UUID, warehouse_id: UUID
) -> None:
    row = await owned(
        session, Warehouse, warehouse_id, tenant_id, "No se encontró el almacén"
    )
    stock = await session.exec(
        select(WarehouseStock).where(
            WarehouseStock.tenant_id == tenant_id,
            WarehouseStock.warehouse_id == warehouse_id,
        )
    )
    movements = await session.exec(
        select(InventoryMovement).where(
            InventoryMovement.tenant_id == tenant_id,
            InventoryMovement.warehouse_id == warehouse_id,
        )
    )
    if stock.first() is not None or movements.first() is not None:
        raise conflict(
            "No se puede eliminar el almacén porque todavía tiene existencias o movimientos"
        )
    await session.delete(row)


async def list_ingredients(
    session: AsyncSession, tenant_id: UUID
) -> list[IngredientRead]:
    rows = await _ingredients(session, tenant_id)
    suppliers = {row.id: row.name for row in await _suppliers(session, tenant_id)}
    return [_ingredient_read(row, suppliers) for row in rows]


async def create_ingredient(
    session: AsyncSession, tenant_id: UUID, data: IngredientIn
) -> IngredientRead:
    if data.supplier_id is not None:
        await owned(
            session,
            Supplier,
            data.supplier_id,
            tenant_id,
            "No se encontró el proveedor",
        )
    waste, yield_factor = _factors(data.waste_factor, data.cooking_yield_factor)
    minimum, maximum = _stock_bounds(data.min_stock, data.max_stock)
    row = Ingredient(
        tenant_id=tenant_id,
        supplier_id=data.supplier_id,
        name=clean_name(data.name),
        unit=data.unit,
        purchase_price=clean_money(data.purchase_price, "El precio de compra"),
        sale_price=_optional_money(data.sale_price, "El precio de venta"),
        min_stock=minimum,
        max_stock=maximum,
        waste_factor=waste,
        cooking_yield_factor=yield_factor,
    )
    session.add(row)
    await session.flush()
    suppliers = {item.id: item.name for item in await _suppliers(session, tenant_id)}
    return _ingredient_read(row, suppliers)


async def update_ingredient(
    session: AsyncSession,
    tenant_id: UUID,
    ingredient_id: UUID,
    data: IngredientUpdate,
) -> IngredientRead:
    row = await owned(
        session, Ingredient, ingredient_id, tenant_id, "No se encontró el insumo"
    )
    fields = data.model_fields_set
    if "name" in fields and data.name is not None:
        row.name = clean_name(data.name)
    if "unit" in fields and data.unit is not None:
        row.unit = data.unit
    if "purchase_price" in fields and data.purchase_price is not None:
        row.purchase_price = clean_money(data.purchase_price, "El precio de compra")
    if data.clear_sale_price or ("sale_price" in fields and data.sale_price is None):
        row.sale_price = None
    elif data.sale_price is not None:
        row.sale_price = _optional_money(data.sale_price, "El precio de venta")
    if data.clear_supplier or ("supplier_id" in fields and data.supplier_id is None):
        row.supplier_id = None
    elif data.supplier_id is not None:
        await owned(
            session,
            Supplier,
            data.supplier_id,
            tenant_id,
            "No se encontró el proveedor",
        )
        row.supplier_id = data.supplier_id
    waste = data.waste_factor if data.waste_factor is not None else row.waste_factor
    yield_factor = (
        data.cooking_yield_factor
        if data.cooking_yield_factor is not None
        else row.cooking_yield_factor
    )
    if "waste_factor" in fields or "cooking_yield_factor" in fields:
        row.waste_factor, row.cooking_yield_factor = _factors(waste, yield_factor)
    minimum = data.min_stock if data.min_stock is not None else row.min_stock
    maximum = data.max_stock if data.max_stock is not None else row.max_stock
    if "min_stock" in fields or "max_stock" in fields:
        row.min_stock, row.max_stock = _stock_bounds(minimum, maximum)
    session.add(row)
    await session.flush()
    suppliers = {item.id: item.name for item in await _suppliers(session, tenant_id)}
    return _ingredient_read(row, suppliers)


async def delete_ingredient(
    session: AsyncSession, tenant_id: UUID, ingredient_id: UUID
) -> None:
    row = await owned(
        session, Ingredient, ingredient_id, tenant_id, "No se encontró el insumo"
    )
    items = await session.exec(
        select(RecipeItem).where(
            RecipeItem.tenant_id == tenant_id,
            RecipeItem.ingredient_id == ingredient_id,
        )
    )
    extras = await session.exec(
        select(MenuExtra).where(
            MenuExtra.tenant_id == tenant_id,
            MenuExtra.ingredient_id == ingredient_id,
        )
    )
    stock = await session.exec(
        select(WarehouseStock).where(
            WarehouseStock.tenant_id == tenant_id,
            WarehouseStock.ingredient_id == ingredient_id,
        )
    )
    movements = await session.exec(
        select(InventoryMovement).where(
            InventoryMovement.tenant_id == tenant_id,
            InventoryMovement.ingredient_id == ingredient_id,
        )
    )
    if (
        items.first() is not None
        or extras.first() is not None
        or stock.first() is not None
        or movements.first() is not None
    ):
        raise conflict(
            "No se puede eliminar el insumo porque todavía se usa en recetas, extras o almacén"
        )
    await session.delete(row)


async def list_stock(
    session: AsyncSession,
    tenant_id: UUID,
    *,
    warehouse_id: UUID | None = None,
) -> list[StockRead]:
    if warehouse_id is not None:
        await owned(
            session, Warehouse, warehouse_id, tenant_id, "No se encontró el almacén"
        )
    statement = select(WarehouseStock).where(WarehouseStock.tenant_id == tenant_id)
    if warehouse_id is not None:
        statement = statement.where(WarehouseStock.warehouse_id == warehouse_id)
    result = await session.exec(statement)
    warehouses = {row.id: row.name for row in await _warehouses(session, tenant_id)}
    ingredients = {row.id: row for row in await _ingredients(session, tenant_id)}
    reads: list[StockRead] = []
    for stock in result.all():
        ingredient = ingredients.get(stock.ingredient_id)
        reads.append(
            StockRead(
                warehouse_id=stock.warehouse_id,
                warehouse_name=warehouses.get(stock.warehouse_id, "Almacén"),
                ingredient_id=stock.ingredient_id,
                ingredient_name=ingredient.name if ingredient else "Insumo",
                unit=ingredient.unit if ingredient else IngredientUnit.PZ,
                physical_stock=stock.physical_stock,
                committed_stock=stock.committed_stock,
                available_stock=stock.available_stock,
            )
        )
    reads.sort(
        key=lambda row: (row.warehouse_name.lower(), row.ingredient_name.lower())
    )
    return reads


async def record_movement(
    session: AsyncSession, tenant_id: UUID, data: MovementIn
) -> MovementRead:
    movement = await apply_movement(
        session,
        tenant_id=tenant_id,
        warehouse_id=data.warehouse_id,
        ingredient_id=data.ingredient_id,
        movement_type=data.movement_type,
        quantity=data.quantity,
        reference_id=data.reference_id,
    )
    return await _movement_read(session, movement)


async def list_movements(
    session: AsyncSession,
    tenant_id: UUID,
    *,
    warehouse_id: UUID | None = None,
    ingredient_id: UUID | None = None,
) -> list[MovementRead]:
    rows = await list_kardex(
        session,
        tenant_id=tenant_id,
        warehouse_id=warehouse_id,
        ingredient_id=ingredient_id,
    )
    warehouses = {row.id: row.name for row in await _warehouses(session, tenant_id)}
    ingredients = {row.id: row.name for row in await _ingredients(session, tenant_id)}
    return [
        MovementRead(
            id=row.id,
            warehouse_id=row.warehouse_id,
            warehouse_name=warehouses.get(row.warehouse_id, "Almacén"),
            ingredient_id=row.ingredient_id,
            ingredient_name=ingredients.get(row.ingredient_id, "Insumo"),
            movement_type=row.movement_type,
            quantity=row.quantity,
            reference_id=row.reference_id,
            created_at=row.created_at.strftime("%d/%m/%Y %H:%M"),
        )
        for row in rows
    ]


def parse_unit(value: str) -> IngredientUnit:
    return as_enum(IngredientUnit, value, "La unidad no es válida")


def parse_movement(value: str) -> MovementType:
    return as_enum(MovementType, value, "El tipo de movimiento no es válido")


async def _movement_read(
    session: AsyncSession, movement: InventoryMovement
) -> MovementRead:
    warehouse = await session.get(Warehouse, movement.warehouse_id)
    ingredient = await session.get(Ingredient, movement.ingredient_id)
    return MovementRead(
        id=movement.id,
        warehouse_id=movement.warehouse_id,
        warehouse_name=warehouse.name if warehouse else "Almacén",
        ingredient_id=movement.ingredient_id,
        ingredient_name=ingredient.name if ingredient else "Insumo",
        movement_type=movement.movement_type,
        quantity=movement.quantity,
        reference_id=movement.reference_id,
        created_at=movement.created_at.strftime("%d/%m/%Y %H:%M"),
    )


def _supplier_read(row: Supplier) -> SupplierRead:
    return SupplierRead(
        id=row.id,
        name=row.name,
        contact_name=row.contact_name,
        phone=row.phone,
        email=row.email,
        notes=row.notes,
    )


def _warehouse_read(row: Warehouse) -> WarehouseRead:
    return WarehouseRead(
        id=row.id,
        name=row.name,
        is_primary=row.is_primary,
        location_notes=row.location_notes,
    )


def _ingredient_read(row: Ingredient, suppliers: dict[UUID, str]) -> IngredientRead:
    return IngredientRead(
        id=row.id,
        supplier_id=row.supplier_id,
        supplier_name=suppliers.get(row.supplier_id) if row.supplier_id else None,
        name=row.name,
        unit=row.unit,
        purchase_price=row.purchase_price,
        sale_price=row.sale_price,
        min_stock=row.min_stock,
        max_stock=row.max_stock,
        waste_factor=row.waste_factor,
        cooking_yield_factor=row.cooking_yield_factor,
    )


async def _keep_one_primary(
    session: AsyncSession, tenant_id: UUID, warehouse_id: UUID
) -> None:
    result = await session.exec(
        select(Warehouse).where(Warehouse.tenant_id == tenant_id)
    )
    for row in result.all():
        if row.id != warehouse_id and row.is_primary:
            row.is_primary = False
            session.add(row)


def _factors(waste_factor: float, cooking_yield_factor: float) -> tuple[float, float]:
    waste = Decimal(str(waste_factor))
    yield_factor = Decimal(str(cooking_yield_factor))
    if waste < 0 or waste >= Decimal("0.95"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="La merma debe ser mayor o igual a 0 y menor a 0.95",
        )
    if yield_factor < Decimal("0.10") or yield_factor > Decimal("1.50"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="El rendimiento debe estar entre 0.10 y 1.50",
        )
    return float(waste), float(yield_factor)


def _stock_bounds(min_stock: float, max_stock: float) -> tuple[float, float]:
    if min_stock < 0 or max_stock < 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="El stock mínimo y el máximo no pueden ser negativos",
        )
    if max_stock < min_stock:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="El stock máximo no puede ser menor que el mínimo",
        )
    return min_stock, max_stock


def _optional_money(value: Decimal | None, label: str) -> Decimal | None:
    if value is None:
        return None
    return clean_money(value, label)


async def _suppliers(session: AsyncSession, tenant_id: UUID) -> list[Supplier]:
    result = await session.exec(select(Supplier).where(Supplier.tenant_id == tenant_id))
    rows = list(result.all())
    rows.sort(key=lambda row: row.name.lower())
    return rows


async def _warehouses(session: AsyncSession, tenant_id: UUID) -> list[Warehouse]:
    result = await session.exec(
        select(Warehouse).where(Warehouse.tenant_id == tenant_id)
    )
    rows = list(result.all())
    rows.sort(key=lambda row: row.name.lower())
    return rows


async def _ingredients(session: AsyncSession, tenant_id: UUID) -> list[Ingredient]:
    result = await session.exec(
        select(Ingredient).where(Ingredient.tenant_id == tenant_id)
    )
    rows = list(result.all())
    rows.sort(key=lambda row: row.name.lower())
    return rows
