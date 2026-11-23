from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.models.enums import IngredientUnit, MovementType
from app.models.inventory import Ingredient, Warehouse
from app.services.cost_engine import IngredientNeed
from app.services.inventory_service import (
    apply_movement,
    commit_recipe_explosion,
    list_kardex,
)
from tests.memory_db import MemorySession


@pytest.mark.asyncio
async def test_purchase_reserve_and_available_stock() -> None:
    session = MemorySession()
    tenant_id = uuid4()
    warehouse = Warehouse(tenant_id=tenant_id, name="Central", is_primary=True)
    ingredient = Ingredient(
        tenant_id=tenant_id,
        name="Arroz",
        unit=IngredientUnit.KG,
        purchase_price=Decimal("10.00"),
        min_stock=0,
        max_stock=20,
        waste_factor=0,
        cooking_yield_factor=1,
    )
    session.add(warehouse)
    session.add(ingredient)

    await apply_movement(
        session,  # type: ignore[arg-type]
        tenant_id=tenant_id,
        warehouse_id=warehouse.id,
        ingredient_id=ingredient.id,
        movement_type=MovementType.PURCHASE_IN,
        quantity=5,
    )
    await apply_movement(
        session,  # type: ignore[arg-type]
        tenant_id=tenant_id,
        warehouse_id=warehouse.id,
        ingredient_id=ingredient.id,
        movement_type=MovementType.COMMIT_RESERVE,
        quantity=2,
    )
    from app.models.inventory import WarehouseStock

    stored = list(session.rows[WarehouseStock].values())
    assert len(stored) == 1
    assert stored[0].physical_stock == 5
    assert stored[0].committed_stock == 2
    assert stored[0].available_stock == 3

    with pytest.raises(HTTPException) as rejected:
        await apply_movement(
            session,  # type: ignore[arg-type]
            tenant_id=tenant_id,
            warehouse_id=warehouse.id,
            ingredient_id=ingredient.id,
            movement_type=MovementType.COMMIT_RESERVE,
            quantity=4,
        )
    assert rejected.value.status_code == 409
    assert stored[0].committed_stock == 2

    kardex = await list_kardex(session, tenant_id=tenant_id)  # type: ignore[arg-type]
    assert len(kardex) == 2
    assert kardex[0].movement_type is MovementType.COMMIT_RESERVE


@pytest.mark.asyncio
async def test_commit_explosion_uses_the_primary_warehouse() -> None:
    session = MemorySession()
    tenant_id = uuid4()
    warehouse = Warehouse(tenant_id=tenant_id, name="Bodega", is_primary=True)
    ingredient = Ingredient(
        tenant_id=tenant_id,
        name="Pollo",
        unit=IngredientUnit.KG,
        purchase_price=Decimal("80.00"),
        min_stock=0,
        max_stock=10,
        waste_factor=0.2,
        cooking_yield_factor=0.8,
    )
    session.add(warehouse)
    session.add(ingredient)
    await apply_movement(
        session,  # type: ignore[arg-type]
        tenant_id=tenant_id,
        warehouse_id=warehouse.id,
        ingredient_id=ingredient.id,
        movement_type=MovementType.PURCHASE_IN,
        quantity=2,
    )
    movements = await commit_recipe_explosion(
        session,  # type: ignore[arg-type]
        tenant_id=tenant_id,
        lines=[IngredientNeed(ingredient.id, 1, 1.5625, Decimal("125.00"))],
    )
    assert len(movements) == 1
    assert movements[0].warehouse_id == warehouse.id
    from app.models.inventory import WarehouseStock

    stock = next(iter(session.rows[WarehouseStock].values()))
    assert stock.physical_stock == 2
    assert stock.committed_stock == 1.5625
    assert stock.available_stock == pytest.approx(0.4375)
