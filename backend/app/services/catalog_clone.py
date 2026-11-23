"""Copy the platform recipe base into a new provider."""

from dataclasses import dataclass
from uuid import UUID

from fastapi import HTTPException, status
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.inventory import Ingredient
from app.models.menu import Recipe, RecipeItem
from app.models.tenant import Tenant
from app.services.concierge import MASTER_CATALOG_ORG_ID


@dataclass(frozen=True)
class CloneResult:
    ingredients: int
    recipes: int


async def clone_master_catalog(session: AsyncSession, target_id: UUID) -> CloneResult:
    master = await _master(session)
    if target_id == master.id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="El catálogo maestro no se clona sobre sí mismo",
        )
    target = await session.get(Tenant, target_id)
    if target is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No se encontró el proveedor",
        )
    ingredient_ids = await _copy_ingredients(session, master.id, target.id)
    recipe_ids, created = await _copy_recipes(session, master.id, target.id)
    await _copy_items(
        session, master.id, target.id, ingredient_ids, recipe_ids, created
    )
    return CloneResult(ingredients=len(ingredient_ids), recipes=len(created))


async def _master(session: AsyncSession) -> Tenant:
    result = await session.exec(
        select(Tenant).where(Tenant.nuna_org_id == MASTER_CATALOG_ORG_ID)
    )
    tenant = result.first()
    if tenant is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No hay catálogo maestro",
        )
    return tenant


async def _copy_ingredients(
    session: AsyncSession, source_id: UUID, target_id: UUID
) -> dict[UUID, UUID]:
    source = await _ingredients(session, source_id)
    existing = {
        row.name.lower(): row.id for row in await _ingredients(session, target_id)
    }
    mapping: dict[UUID, UUID] = {}
    for row in source:
        found = existing.get(row.name.lower())
        if found is not None:
            mapping[row.id] = found
            continue
        clone = Ingredient(
            tenant_id=target_id,
            name=row.name,
            unit=row.unit,
            purchase_price=row.purchase_price,
            sale_price=row.sale_price,
            min_stock=row.min_stock,
            max_stock=row.max_stock,
            waste_factor=row.waste_factor,
            cooking_yield_factor=row.cooking_yield_factor,
        )
        session.add(clone)
        await session.flush()
        mapping[row.id] = clone.id
        existing[row.name.lower()] = clone.id
    return mapping


async def _copy_recipes(
    session: AsyncSession, source_id: UUID, target_id: UUID
) -> tuple[dict[UUID, UUID], set[UUID]]:
    source = await _recipes(session, source_id)
    existing = {row.name.lower(): row.id for row in await _recipes(session, target_id)}
    mapping: dict[UUID, UUID] = {}
    created: set[UUID] = set()
    for row in source:
        found = existing.get(row.name.lower())
        if found is not None:
            mapping[row.id] = found
            continue
        clone = Recipe(
            tenant_id=target_id,
            name=row.name,
            is_sub_recipe=row.is_sub_recipe,
            portion_size=row.portion_size,
            portion_unit=row.portion_unit,
        )
        session.add(clone)
        await session.flush()
        mapping[row.id] = clone.id
        existing[row.name.lower()] = clone.id
        created.add(clone.id)
    return mapping, created


async def _copy_items(
    session: AsyncSession,
    source_id: UUID,
    target_id: UUID,
    ingredients: dict[UUID, UUID],
    recipes: dict[UUID, UUID],
    created_recipes: set[UUID],
) -> None:
    seen = {
        (row.recipe_id, row.ingredient_id, row.sub_recipe_id, row.net_qty_per_portion)
        for row in await _items(session, target_id)
    }
    for row in await _items(session, source_id):
        recipe_id = recipes.get(row.recipe_id)
        if recipe_id is None or recipe_id not in created_recipes:
            continue
        ingredient_id = (
            ingredients.get(row.ingredient_id)
            if row.ingredient_id is not None
            else None
        )
        sub_recipe_id = (
            recipes.get(row.sub_recipe_id) if row.sub_recipe_id is not None else None
        )
        if row.ingredient_id is not None and ingredient_id is None:
            continue
        if row.sub_recipe_id is not None and sub_recipe_id is None:
            continue
        key = (recipe_id, ingredient_id, sub_recipe_id, row.net_qty_per_portion)
        if key in seen:
            continue
        session.add(
            RecipeItem(
                tenant_id=target_id,
                recipe_id=recipe_id,
                ingredient_id=ingredient_id,
                sub_recipe_id=sub_recipe_id,
                net_qty_per_portion=row.net_qty_per_portion,
            )
        )
        seen.add(key)
    await session.flush()


async def _ingredients(session: AsyncSession, tenant_id: UUID) -> list[Ingredient]:
    result = await session.exec(
        select(Ingredient).where(Ingredient.tenant_id == tenant_id)
    )
    return list(result.all())


async def _recipes(session: AsyncSession, tenant_id: UUID) -> list[Recipe]:
    result = await session.exec(select(Recipe).where(Recipe.tenant_id == tenant_id))
    return list(result.all())


async def _items(session: AsyncSession, tenant_id: UUID) -> list[RecipeItem]:
    result = await session.exec(
        select(RecipeItem).where(RecipeItem.tenant_id == tenant_id)
    )
    return list(result.all())
