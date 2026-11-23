from uuid import UUID

from fastapi import APIRouter, status

from app.api.deps import CurrentActiveTenant, SessionDep
from app.schemas.catalog import (
    CommitIn,
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
    WarehouseUpdate,
)
from app.services import menu_catalog
from app.services import warehouse_catalog as catalog
from app.services.inventory_service import commit_recipe_explosion

router = APIRouter(prefix="/warehouses", tags=["warehouses"])


@router.get("/suppliers", response_model=list[SupplierRead])
async def list_suppliers(
    session: SessionDep, tenant: CurrentActiveTenant
) -> list[SupplierRead]:
    return await catalog.list_suppliers(session, tenant.id)


@router.post(
    "/suppliers", response_model=SupplierRead, status_code=status.HTTP_201_CREATED
)
async def create_supplier(
    session: SessionDep, tenant: CurrentActiveTenant, data: SupplierIn
) -> SupplierRead:
    row = await catalog.create_supplier(session, tenant.id, data)
    await session.commit()
    return row


@router.patch("/suppliers/{supplier_id}", response_model=SupplierRead)
async def update_supplier(
    session: SessionDep,
    tenant: CurrentActiveTenant,
    supplier_id: UUID,
    data: SupplierUpdate,
) -> SupplierRead:
    row = await catalog.update_supplier(session, tenant.id, supplier_id, data)
    await session.commit()
    return row


@router.delete("/suppliers/{supplier_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_supplier(
    session: SessionDep, tenant: CurrentActiveTenant, supplier_id: UUID
) -> None:
    await catalog.delete_supplier(session, tenant.id, supplier_id)
    await session.commit()


@router.get("/ingredients", response_model=list[IngredientRead])
async def list_ingredients(
    session: SessionDep, tenant: CurrentActiveTenant
) -> list[IngredientRead]:
    return await catalog.list_ingredients(session, tenant.id)


@router.post(
    "/ingredients", response_model=IngredientRead, status_code=status.HTTP_201_CREATED
)
async def create_ingredient(
    session: SessionDep, tenant: CurrentActiveTenant, data: IngredientIn
) -> IngredientRead:
    row = await catalog.create_ingredient(session, tenant.id, data)
    await session.commit()
    return row


@router.patch("/ingredients/{ingredient_id}", response_model=IngredientRead)
async def update_ingredient(
    session: SessionDep,
    tenant: CurrentActiveTenant,
    ingredient_id: UUID,
    data: IngredientUpdate,
) -> IngredientRead:
    row = await catalog.update_ingredient(session, tenant.id, ingredient_id, data)
    await session.commit()
    return row


@router.delete("/ingredients/{ingredient_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_ingredient(
    session: SessionDep, tenant: CurrentActiveTenant, ingredient_id: UUID
) -> None:
    await catalog.delete_ingredient(session, tenant.id, ingredient_id)
    await session.commit()


@router.get("/stock", response_model=list[StockRead])
async def list_stock(
    session: SessionDep,
    tenant: CurrentActiveTenant,
    warehouse_id: UUID | None = None,
) -> list[StockRead]:
    return await catalog.list_stock(session, tenant.id, warehouse_id=warehouse_id)


@router.get("/kardex", response_model=list[MovementRead])
async def list_kardex(
    session: SessionDep,
    tenant: CurrentActiveTenant,
    warehouse_id: UUID | None = None,
    ingredient_id: UUID | None = None,
) -> list[MovementRead]:
    return await catalog.list_movements(
        session,
        tenant.id,
        warehouse_id=warehouse_id,
        ingredient_id=ingredient_id,
    )


@router.post(
    "/movements", response_model=MovementRead, status_code=status.HTTP_201_CREATED
)
async def create_movement(
    session: SessionDep, tenant: CurrentActiveTenant, data: MovementIn
) -> MovementRead:
    row = await catalog.record_movement(session, tenant.id, data)
    await session.commit()
    return row


@router.post(
    "/reservations",
    response_model=list[MovementRead],
    status_code=status.HTTP_201_CREATED,
)
async def reserve_recipe(
    session: SessionDep, tenant: CurrentActiveTenant, data: CommitIn
) -> list[MovementRead]:
    lines = await menu_catalog.explosion_for_recipe(
        session, tenant.id, data.recipe_id, data.portions
    )
    movements = await commit_recipe_explosion(
        session,
        tenant_id=tenant.id,
        lines=lines,
        reference_id=data.reference_id,
    )
    created = {row.id for row in movements}
    listed = await catalog.list_movements(session, tenant.id)
    await session.commit()
    return [row for row in listed if row.id in created]


@router.get("", response_model=list[WarehouseRead])
async def list_warehouses(
    session: SessionDep, tenant: CurrentActiveTenant
) -> list[WarehouseRead]:
    return await catalog.list_warehouses(session, tenant.id)


@router.post("", response_model=WarehouseRead, status_code=status.HTTP_201_CREATED)
async def create_warehouse(
    session: SessionDep, tenant: CurrentActiveTenant, data: WarehouseIn
) -> WarehouseRead:
    row = await catalog.create_warehouse(session, tenant.id, data)
    await session.commit()
    return row


@router.patch("/{warehouse_id}", response_model=WarehouseRead)
async def update_warehouse(
    session: SessionDep,
    tenant: CurrentActiveTenant,
    warehouse_id: UUID,
    data: WarehouseUpdate,
) -> WarehouseRead:
    row = await catalog.update_warehouse(session, tenant.id, warehouse_id, data)
    await session.commit()
    return row


@router.delete("/{warehouse_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_warehouse(
    session: SessionDep, tenant: CurrentActiveTenant, warehouse_id: UUID
) -> None:
    await catalog.delete_warehouse(session, tenant.id, warehouse_id)
    await session.commit()
