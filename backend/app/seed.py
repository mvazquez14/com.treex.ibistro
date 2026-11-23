import logging
from decimal import Decimal

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.core.db import async_session_maker
from app.models import (
    Ingredient,
    IngredientUnit,
    Recipe,
    RecipeItem,
    ServiceCategory,
    Tenant,
)
from app.services.concierge import MASTER_CATALOG_ORG_ID
from app.services.slug import slugify
from app.services.tenants import allocate_unique_slug

logger = logging.getLogger(__name__)

SERVICE_CATEGORIES: tuple[tuple[str, str], ...] = (
    ("Italiana", "italiana"),
    ("Sushi", "sushi"),
    ("Taquiza", "taquiza"),
    ("BBQ", "bbq"),
    ("Mexicana", "mexicana"),
    ("Mariscos", "mariscos"),
    ("Postres", "postres"),
)

DEMO_ORG_ID = "mock-org"
DEMO_BUSINESS_NAME = "Catering Demo"
MASTER_BUSINESS_NAME = "Catálogo maestro"


async def seed() -> None:
    async with async_session_maker() as session:
        for name, icon in SERVICE_CATEGORIES:
            slug = slugify(name)
            result = await session.exec(
                select(ServiceCategory).where(ServiceCategory.slug == slug)
            )
            category = result.first()
            if category:
                category.name = name
                category.icon = icon
                category.is_active = True
                session.add(category)
            else:
                session.add(
                    ServiceCategory(name=name, slug=slug, icon=icon, is_active=True)
                )
        if settings.MOCK_MODE:
            await _ensure_demo_tenant(session)
        await _ensure_master_catalog(session)
        await session.commit()
    logger.info("Seed data is ready")


async def _ensure_demo_tenant(session: AsyncSession) -> None:
    result = await session.exec(select(Tenant).where(Tenant.nuna_org_id == DEMO_ORG_ID))
    if result.first():
        return
    slug = await allocate_unique_slug(session, DEMO_BUSINESS_NAME)
    session.add(
        Tenant(
            nuna_org_id=DEMO_ORG_ID,
            slug=slug,
            business_name=DEMO_BUSINESS_NAME,
            rfc="XAXX010101000",
            address="Guadalajara, Jalisco",
            has_active_plan=True,
        )
    )


async def _ensure_master_catalog(session: AsyncSession) -> None:
    result = await session.exec(
        select(Tenant).where(Tenant.nuna_org_id == MASTER_CATALOG_ORG_ID)
    )
    tenant = result.first()
    if tenant is None:
        slug = await allocate_unique_slug(session, MASTER_BUSINESS_NAME)
        tenant = Tenant(
            nuna_org_id=MASTER_CATALOG_ORG_ID,
            slug=slug,
            business_name=MASTER_BUSINESS_NAME,
            has_active_plan=False,
            is_verified_concierge=False,
        )
        session.add(tenant)
        await session.flush()
    await _ensure_master_recipes(session, tenant)


async def _ensure_master_recipes(session: AsyncSession, tenant: Tenant) -> None:
    ingredients = await session.exec(
        select(Ingredient).where(Ingredient.tenant_id == tenant.id)
    )
    by_name = {row.name.lower(): row for row in ingredients.all()}
    arroz = by_name.get("arroz") or _ingredient(session, tenant, "Arroz")
    pollo = by_name.get("pollo") or _ingredient(session, tenant, "Pollo")
    await session.flush()
    recipes = await session.exec(select(Recipe).where(Recipe.tenant_id == tenant.id))
    if any(row.name.lower() == "arroz con pollo" for row in recipes.all()):
        return
    recipe = Recipe(
        tenant_id=tenant.id,
        name="Arroz con pollo",
        portion_size=1,
        portion_unit="porción",
    )
    session.add(recipe)
    await session.flush()
    session.add(
        RecipeItem(
            tenant_id=tenant.id,
            recipe_id=recipe.id,
            ingredient_id=arroz.id,
            net_qty_per_portion=0.08,
        )
    )
    session.add(
        RecipeItem(
            tenant_id=tenant.id,
            recipe_id=recipe.id,
            ingredient_id=pollo.id,
            net_qty_per_portion=0.12,
        )
    )


def _ingredient(session: AsyncSession, tenant: Tenant, name: str) -> Ingredient:
    row = Ingredient(
        tenant_id=tenant.id,
        name=name,
        unit=IngredientUnit.KG,
        purchase_price=Decimal("40.00"),
        min_stock=0,
        max_stock=20,
        waste_factor=0,
        cooking_yield_factor=1,
    )
    session.add(row)
    return row


def main() -> None:
    import asyncio

    logging.basicConfig(level=logging.INFO)
    asyncio.run(seed())


if __name__ == "__main__":
    main()
