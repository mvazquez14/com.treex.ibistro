"""Recipes, packages, and extras for one tenant."""

from decimal import Decimal
from uuid import UUID

from fastapi import HTTPException, status
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.inventory import Ingredient
from app.models.menu import (
    CateringPackage,
    ExtraCategory,
    MenuExtra,
    PackageGroupOption,
    PackageRecipeGroup,
    Recipe,
    RecipeItem,
)
from app.models.tenant import ServiceCategory
from app.schemas.catalog import (
    CategoryRead,
    ExtraIn,
    ExtraRead,
    ExtraUpdate,
    MenuScreen,
    NeedRead,
    PackageGroupIn,
    PackageGroupRead,
    PackageGroupUpdate,
    PackageIn,
    PackageOptionIn,
    PackageOptionRead,
    PackageRead,
    PackageUpdate,
    QuoteIn,
    QuoteRead,
    RecipeIn,
    RecipeItemIn,
    RecipeItemRead,
    RecipePreview,
    RecipeRead,
    RecipeUpdate,
)
from app.services.catalog_common import (
    clean_money,
    clean_name,
    clean_optional,
    clean_text,
    conflict,
    owned,
    require_portion,
)
from app.services.cost_engine import (
    CostError,
    ExtraCharge,
    IngredientCost,
    IngredientNeed,
    PackageGroup,
    PackageOption,
    RecipeCost,
    RecipeLine,
    explode_recipe,
    gross_quantity,
    quote_package,
    recipe_cost,
)
from app.services.warehouse_catalog import list_ingredients


async def menu_snapshot(session: AsyncSession, tenant_id: UUID) -> MenuScreen:
    return MenuScreen(
        recipes=await list_recipes(session, tenant_id),
        packages=await list_packages(session, tenant_id),
        extras=await list_extras(session, tenant_id),
        ingredients=await list_ingredients(session, tenant_id),
        categories=await _categories(session),
    )


async def list_recipes(session: AsyncSession, tenant_id: UUID) -> list[RecipeRead]:
    recipes = await _recipes(session, tenant_id)
    items = await _items(session, tenant_id)
    ingredients = await _ingredient_rows(session, tenant_id)
    nodes, costs = _engine_maps(recipes, items, ingredients)
    ingredient_names = {row.id: row.name for row in ingredients}
    recipe_names = {row.id: row.name for row in recipes}
    grouped: dict[UUID, list[RecipeItem]] = {}
    for item in items:
        grouped.setdefault(item.recipe_id, []).append(item)
    reads: list[RecipeRead] = []
    for recipe in recipes:
        cost, note = _portion_cost(recipe.id, nodes, costs)
        lines = grouped.get(recipe.id, [])
        lines.sort(key=lambda row: str(row.id))
        reads.append(
            RecipeRead(
                id=recipe.id,
                name=recipe.name,
                is_sub_recipe=recipe.is_sub_recipe,
                portion_size=recipe.portion_size,
                portion_unit=recipe.portion_unit,
                cost_per_portion=cost,
                cost_note=note,
                items=[
                    _item_read(item, ingredient_names, recipe_names, ingredients)
                    for item in lines
                ],
            )
        )
    return reads


async def create_recipe(
    session: AsyncSession, tenant_id: UUID, data: RecipeIn
) -> RecipeRead:
    row = Recipe(
        tenant_id=tenant_id,
        name=clean_name(data.name),
        is_sub_recipe=data.is_sub_recipe,
        portion_size=require_portion(
            data.portion_size, "El tamaño de porción debe ser mayor a cero"
        ),
        portion_unit=_portion_unit(data.portion_unit),
    )
    session.add(row)
    await session.flush()
    return await _recipe_read(session, tenant_id, row.id)


async def update_recipe(
    session: AsyncSession,
    tenant_id: UUID,
    recipe_id: UUID,
    data: RecipeUpdate,
) -> RecipeRead:
    row = await owned(session, Recipe, recipe_id, tenant_id, "No se encontró la receta")
    fields = data.model_fields_set
    if "name" in fields and data.name is not None:
        row.name = clean_name(data.name)
    if "portion_size" in fields and data.portion_size is not None:
        row.portion_size = require_portion(
            data.portion_size, "El tamaño de porción debe ser mayor a cero"
        )
    if "portion_unit" in fields and data.portion_unit is not None:
        row.portion_unit = _portion_unit(data.portion_unit)
    if "is_sub_recipe" in fields and data.is_sub_recipe is not None:
        row.is_sub_recipe = data.is_sub_recipe
    session.add(row)
    await session.flush()
    return await _recipe_read(session, tenant_id, row.id)


async def delete_recipe(
    session: AsyncSession, tenant_id: UUID, recipe_id: UUID
) -> None:
    await owned(session, Recipe, recipe_id, tenant_id, "No se encontró la receta")
    if await _items_of(session, tenant_id, recipe_id):
        raise conflict("No se puede eliminar la receta porque todavía tiene líneas")
    if await _sub_recipe_uses(session, tenant_id, recipe_id):
        raise conflict("No se puede eliminar la receta porque otra receta la usa")
    if await _option_uses(session, tenant_id, recipe_id):
        raise conflict("No se puede eliminar la receta porque está en un paquete")
    if await _extra_recipe_uses(session, tenant_id, recipe_id):
        raise conflict("No se puede eliminar la receta porque un extra la usa")
    row = await owned(session, Recipe, recipe_id, tenant_id, "No se encontró la receta")
    await session.delete(row)


async def add_recipe_item(
    session: AsyncSession,
    tenant_id: UUID,
    recipe_id: UUID,
    data: RecipeItemIn,
) -> RecipeRead:
    await owned(session, Recipe, recipe_id, tenant_id, "No se encontró la receta")
    ingredient_id, sub_recipe_id = await _line_targets(
        session,
        tenant_id,
        recipe_id,
        data.ingredient_id,
        data.sub_recipe_id,
    )
    session.add(
        RecipeItem(
            tenant_id=tenant_id,
            recipe_id=recipe_id,
            ingredient_id=ingredient_id,
            sub_recipe_id=sub_recipe_id,
            net_qty_per_portion=require_portion(
                data.net_qty_per_portion,
                "La cantidad neta debe ser mayor a cero",
            ),
        )
    )
    await session.flush()
    return await _recipe_read(session, tenant_id, recipe_id)


async def update_recipe_item(
    session: AsyncSession,
    tenant_id: UUID,
    item_id: UUID,
    data: RecipeItemIn,
) -> RecipeRead:
    row = await owned(
        session, RecipeItem, item_id, tenant_id, "No se encontró la línea"
    )
    ingredient_id, sub_recipe_id = await _line_targets(
        session,
        tenant_id,
        row.recipe_id,
        data.ingredient_id,
        data.sub_recipe_id,
    )
    row.ingredient_id = ingredient_id
    row.sub_recipe_id = sub_recipe_id
    row.net_qty_per_portion = require_portion(
        data.net_qty_per_portion,
        "La cantidad neta debe ser mayor a cero",
    )
    session.add(row)
    await session.flush()
    return await _recipe_read(session, tenant_id, row.recipe_id)


async def preview_recipe(
    session: AsyncSession,
    tenant_id: UUID,
    recipe_id: UUID,
    items: list[RecipeItemIn],
) -> RecipePreview:
    await owned(session, Recipe, recipe_id, tenant_id, "No se encontró la receta")
    recipes = await _recipes(session, tenant_id)
    ingredients = await _ingredient_rows(session, tenant_id)
    kept = [
        item
        for item in await _items(session, tenant_id)
        if item.recipe_id != recipe_id
    ]
    drafts: list[RecipeItem] = []
    for data in items:
        ingredient_id, sub_recipe_id = await _line_targets(
            session,
            tenant_id,
            recipe_id,
            data.ingredient_id,
            data.sub_recipe_id,
        )
        drafts.append(
            RecipeItem(
                tenant_id=tenant_id,
                recipe_id=recipe_id,
                ingredient_id=ingredient_id,
                sub_recipe_id=sub_recipe_id,
                net_qty_per_portion=require_portion(
                    data.net_qty_per_portion,
                    "La cantidad neta debe ser mayor a cero",
                ),
            )
        )
    nodes, costs = _engine_maps(recipes, kept + drafts, ingredients)
    cost, note = _portion_cost(recipe_id, nodes, costs)
    return RecipePreview(cost_per_portion=cost, cost_note=note)


async def delete_recipe_item(
    session: AsyncSession, tenant_id: UUID, item_id: UUID
) -> None:
    row = await owned(
        session, RecipeItem, item_id, tenant_id, "No se encontró la línea"
    )
    await session.delete(row)


async def list_packages(session: AsyncSession, tenant_id: UUID) -> list[PackageRead]:
    packages = await _packages(session, tenant_id)
    groups = await _groups(session, tenant_id)
    options = await _options(session, tenant_id)
    recipes = await _recipes(session, tenant_id)
    categories = {row.id: row.name for row in await _category_rows(session)}
    recipe_names = {row.id: row.name for row in recipes}
    options_by_group: dict[UUID, list[PackageGroupOption]] = {}
    for option in options:
        options_by_group.setdefault(option.group_id, []).append(option)
    groups_by_package: dict[UUID, list[PackageRecipeGroup]] = {}
    for group in groups:
        groups_by_package.setdefault(group.package_id, []).append(group)
    reads: list[PackageRead] = []
    for package in packages:
        package_groups = groups_by_package.get(package.id, [])
        package_groups.sort(key=lambda row: row.group_name.lower())
        reads.append(
            PackageRead(
                id=package.id,
                category_id=package.category_id,
                category_name=categories.get(package.category_id, "Sin categoría"),
                name=package.name,
                description=package.description,
                photo_url=package.photo_url,
                base_price_per_guest=package.base_price_per_guest,
                min_guests=package.min_guests,
                is_active=package.is_active,
                groups=[
                    _group_read(group, options_by_group, recipe_names)
                    for group in package_groups
                ],
            )
        )
    return reads


async def create_package(
    session: AsyncSession, tenant_id: UUID, data: PackageIn
) -> PackageRead:
    await _require_category(session, data.category_id)
    row = CateringPackage(
        tenant_id=tenant_id,
        category_id=data.category_id,
        name=clean_name(data.name),
        description=clean_text(data.description),
        photo_url=clean_optional(data.photo_url, limit=2048),
        base_price_per_guest=clean_money(data.base_price_per_guest, "El precio base"),
        min_guests=_min_guests(data.min_guests),
        is_active=data.is_active,
    )
    session.add(row)
    await session.flush()
    return await _package_read(session, tenant_id, row.id)


async def update_package(
    session: AsyncSession,
    tenant_id: UUID,
    package_id: UUID,
    data: PackageUpdate,
) -> PackageRead:
    row = await owned(
        session, CateringPackage, package_id, tenant_id, "No se encontró el paquete"
    )
    fields = data.model_fields_set
    if "category_id" in fields and data.category_id is not None:
        await _require_category(session, data.category_id)
        row.category_id = data.category_id
    if "name" in fields and data.name is not None:
        row.name = clean_name(data.name)
    if "description" in fields:
        row.description = clean_text(data.description)
    if "photo_url" in fields:
        row.photo_url = clean_optional(data.photo_url, limit=2048)
    if "base_price_per_guest" in fields and data.base_price_per_guest is not None:
        row.base_price_per_guest = clean_money(
            data.base_price_per_guest, "El precio base"
        )
    if "min_guests" in fields and data.min_guests is not None:
        row.min_guests = _min_guests(data.min_guests)
    if "is_active" in fields and data.is_active is not None:
        row.is_active = data.is_active
    session.add(row)
    await session.flush()
    return await _package_read(session, tenant_id, row.id)


async def delete_package(
    session: AsyncSession, tenant_id: UUID, package_id: UUID
) -> None:
    row = await owned(
        session, CateringPackage, package_id, tenant_id, "No se encontró el paquete"
    )
    if await _groups_of(session, tenant_id, package_id):
        raise conflict("No se puede eliminar el paquete porque todavía tiene grupos")
    from app.models.equipment import PackageEquipmentRule

    rules = await session.exec(
        select(PackageEquipmentRule).where(
            PackageEquipmentRule.tenant_id == tenant_id,
            PackageEquipmentRule.package_id == package_id,
        )
    )
    if list(rules.all()):
        raise conflict(
            "No se puede eliminar el paquete porque todavía tiene reglas de equipo"
        )
    await session.delete(row)


async def add_group(
    session: AsyncSession,
    tenant_id: UUID,
    package_id: UUID,
    data: PackageGroupIn,
) -> PackageRead:
    await owned(
        session, CateringPackage, package_id, tenant_id, "No se encontró el paquete"
    )
    _check_choices(data.min_choices, data.max_choices, data.is_fixed)
    session.add(
        PackageRecipeGroup(
            tenant_id=tenant_id,
            package_id=package_id,
            group_name=clean_name(data.group_name),
            min_choices=data.min_choices,
            max_choices=data.max_choices,
            is_fixed=data.is_fixed,
        )
    )
    await session.flush()
    return await _package_read(session, tenant_id, package_id)


async def update_group(
    session: AsyncSession,
    tenant_id: UUID,
    group_id: UUID,
    data: PackageGroupUpdate,
) -> PackageRead:
    row = await owned(
        session, PackageRecipeGroup, group_id, tenant_id, "No se encontró el grupo"
    )
    name = (
        clean_name(data.group_name) if data.group_name is not None else row.group_name
    )
    minimum = data.min_choices if data.min_choices is not None else row.min_choices
    maximum = data.max_choices if data.max_choices is not None else row.max_choices
    fixed = data.is_fixed if data.is_fixed is not None else row.is_fixed
    if (
        data.group_name is not None
        or data.min_choices is not None
        or (data.max_choices is not None or data.is_fixed is not None)
    ):
        _check_choices(minimum, maximum, fixed)
    row.group_name = name
    row.min_choices = minimum
    row.max_choices = maximum
    row.is_fixed = fixed
    session.add(row)
    await session.flush()
    return await _package_read(session, tenant_id, row.package_id)


async def delete_group(session: AsyncSession, tenant_id: UUID, group_id: UUID) -> None:
    row = await owned(
        session, PackageRecipeGroup, group_id, tenant_id, "No se encontró el grupo"
    )
    result = await session.exec(
        select(PackageGroupOption).where(
            PackageGroupOption.tenant_id == tenant_id,
            PackageGroupOption.group_id == group_id,
        )
    )
    if list(result.all()):
        raise conflict("No se puede eliminar el grupo porque todavía tiene opciones")
    await session.delete(row)


async def add_option(
    session: AsyncSession,
    tenant_id: UUID,
    group_id: UUID,
    data: PackageOptionIn,
) -> PackageRead:
    group = await owned(
        session, PackageRecipeGroup, group_id, tenant_id, "No se encontró el grupo"
    )
    await owned(session, Recipe, data.recipe_id, tenant_id, "No se encontró la receta")
    existing = await session.exec(
        select(PackageGroupOption).where(
            PackageGroupOption.tenant_id == tenant_id,
            PackageGroupOption.group_id == group_id,
            PackageGroupOption.recipe_id == data.recipe_id,
        )
    )
    if existing.first() is not None:
        raise conflict("Esa receta ya está en el grupo")
    session.add(
        PackageGroupOption(
            tenant_id=tenant_id,
            group_id=group_id,
            recipe_id=data.recipe_id,
            portions_per_guest=require_portion(
                data.portions_per_guest,
                "Las porciones por invitado deben ser mayores a cero",
            ),
            extra_price_per_guest=clean_money(
                data.extra_price_per_guest, "El precio extra"
            ),
        )
    )
    await session.flush()
    return await _package_read(session, tenant_id, group.package_id)


async def delete_option(
    session: AsyncSession, tenant_id: UUID, option_id: UUID
) -> None:
    row = await owned(
        session,
        PackageGroupOption,
        option_id,
        tenant_id,
        "No se encontró la opción",
    )
    await session.delete(row)


async def list_extras(session: AsyncSession, tenant_id: UUID) -> list[ExtraRead]:
    rows = await _extra_rows(session, tenant_id)
    ingredients = {
        row.id: row.name for row in await _ingredient_rows(session, tenant_id)
    }
    recipes = {row.id: row.name for row in await _recipes(session, tenant_id)}
    links = await _extra_category_map(session, tenant_id)
    names = {row.id: row.name for row in await _category_rows(session)}
    return [_extra_read(row, ingredients, recipes, links, names) for row in rows]


async def create_extra(
    session: AsyncSession, tenant_id: UUID, data: ExtraIn
) -> ExtraRead:
    ingredient_id, recipe_id = await _extra_links(
        session, tenant_id, data.ingredient_id, data.recipe_id
    )
    row = MenuExtra(
        tenant_id=tenant_id,
        name=clean_name(data.name),
        ingredient_id=ingredient_id,
        recipe_id=recipe_id,
        unit_price=clean_money(data.unit_price, "El precio"),
        pricing_type=data.pricing_type,
        is_active=data.is_active,
    )
    session.add(row)
    await session.flush()
    await _replace_extra_categories(session, tenant_id, row.id, data.category_ids)
    return await _extra_one(session, tenant_id, row.id)


async def update_extra(
    session: AsyncSession,
    tenant_id: UUID,
    extra_id: UUID,
    data: ExtraUpdate,
) -> ExtraRead:
    row = await owned(
        session, MenuExtra, extra_id, tenant_id, "No se encontró el extra"
    )
    fields = data.model_fields_set
    ingredient_id = row.ingredient_id
    recipe_id = row.recipe_id
    if data.clear_ingredient or (
        "ingredient_id" in fields and data.ingredient_id is None
    ):
        ingredient_id = None
    elif data.ingredient_id is not None:
        ingredient_id = data.ingredient_id
    if data.clear_recipe or ("recipe_id" in fields and data.recipe_id is None):
        recipe_id = None
    elif data.recipe_id is not None:
        recipe_id = data.recipe_id
    if (
        "ingredient_id" in fields
        or "recipe_id" in fields
        or data.clear_ingredient
        or data.clear_recipe
    ):
        ingredient_id, recipe_id = await _extra_links(
            session, tenant_id, ingredient_id, recipe_id
        )
        row.ingredient_id = ingredient_id
        row.recipe_id = recipe_id
    if "name" in fields and data.name is not None:
        row.name = clean_name(data.name)
    if "unit_price" in fields and data.unit_price is not None:
        row.unit_price = clean_money(data.unit_price, "El precio")
    if "pricing_type" in fields and data.pricing_type is not None:
        row.pricing_type = data.pricing_type
    if "is_active" in fields and data.is_active is not None:
        row.is_active = data.is_active
    session.add(row)
    await session.flush()
    if "category_ids" in fields and data.category_ids is not None:
        await _replace_extra_categories(session, tenant_id, row.id, data.category_ids)
    return await _extra_one(session, tenant_id, row.id)


async def delete_extra(session: AsyncSession, tenant_id: UUID, extra_id: UUID) -> None:
    row = await owned(
        session, MenuExtra, extra_id, tenant_id, "No se encontró el extra"
    )
    for link in await _links_for_extra(session, tenant_id, extra_id):
        await session.delete(link)
    await session.delete(row)


async def quote_for_package(
    session: AsyncSession,
    tenant_id: UUID,
    package_id: UUID,
    data: QuoteIn,
) -> QuoteRead:
    package = await _package_read(session, tenant_id, package_id)
    recipes = await _recipes(session, tenant_id)
    items = await _items(session, tenant_id)
    ingredients = await _ingredient_rows(session, tenant_id)
    nodes, costs = _engine_maps(recipes, items, ingredients)
    groups = [
        PackageGroup(
            id=group.id,
            is_fixed=group.is_fixed,
            min_choices=group.min_choices,
            max_choices=group.max_choices,
            options=tuple(
                PackageOption(
                    recipe_id=option.recipe_id,
                    portions_per_guest=option.portions_per_guest,
                    extra_price_per_guest=option.extra_price_per_guest,
                )
                for option in group.options
            ),
        )
        for group in package.groups
    ]
    extra_rows = {row.id: row for row in await _extra_rows(session, tenant_id)}
    charges: list[ExtraCharge] = []
    for requested in data.extras:
        extra = extra_rows.get(requested.extra_id)
        if extra is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No se encontró el extra",
            )
        ingredient = costs.get(extra.ingredient_id) if extra.ingredient_id else None
        if extra.ingredient_id is not None and ingredient is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="No se encontró el insumo",
            )
        charges.append(
            ExtraCharge(
                pricing_type=extra.pricing_type,
                unit_price=extra.unit_price,
                quantity=requested.quantity,
                ingredient=ingredient,
                recipe_id=extra.recipe_id,
            )
        )
    try:
        quoted = quote_package(
            guest_count=data.guest_count,
            base_price_per_guest=package.base_price_per_guest,
            groups=groups,
            selected_options=data.selected_options,
            recipes=nodes,
            ingredients=costs,
            extras=charges,
        )
    except CostError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        )
    names = {row.id: row.name for row in ingredients}
    return QuoteRead(
        cogs=quoted.cogs,
        price=quoted.price,
        price_per_guest=quoted.price_per_guest,
        explosion=[
            NeedRead(
                ingredient_id=line.ingredient_id,
                ingredient_name=names.get(line.ingredient_id, "Insumo"),
                net_qty=line.net_qty,
                gross_qty=line.gross_qty,
                cost=line.cost,
            )
            for line in quoted.explosion
        ],
    )


async def explosion_for_recipe(
    session: AsyncSession,
    tenant_id: UUID,
    recipe_id: UUID,
    portions: float,
) -> tuple[IngredientNeed, ...]:
    await owned(session, Recipe, recipe_id, tenant_id, "No se encontró la receta")
    recipes = await _recipes(session, tenant_id)
    items = await _items(session, tenant_id)
    ingredients = await _ingredient_rows(session, tenant_id)
    nodes, costs = _engine_maps(recipes, items, ingredients)
    try:
        return explode_recipe(recipe_id, nodes, costs, portions=portions)
    except CostError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        )


async def _recipe_read(
    session: AsyncSession, tenant_id: UUID, recipe_id: UUID
) -> RecipeRead:
    for recipe in await list_recipes(session, tenant_id):
        if recipe.id == recipe_id:
            return recipe
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND, detail="No se encontró la receta"
    )


async def _package_read(
    session: AsyncSession, tenant_id: UUID, package_id: UUID
) -> PackageRead:
    for package in await list_packages(session, tenant_id):
        if package.id == package_id:
            return package
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND, detail="No se encontró el paquete"
    )


async def _extra_one(
    session: AsyncSession, tenant_id: UUID, extra_id: UUID
) -> ExtraRead:
    for extra in await list_extras(session, tenant_id):
        if extra.id == extra_id:
            return extra
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND, detail="No se encontró el extra"
    )


def _item_read(
    item: RecipeItem,
    ingredient_names: dict[UUID, str],
    recipe_names: dict[UUID, str],
    ingredients: list[Ingredient] | None = None,
) -> RecipeItemRead:
    catalog = {row.id: row for row in ingredients or []}
    unit: str | None = None
    gross: float | None = None
    if item.ingredient_id is not None:
        label = ingredient_names.get(item.ingredient_id, "Insumo")
        ingredient = catalog.get(item.ingredient_id)
        if ingredient is not None:
            unit = ingredient.unit.value
            gross = gross_quantity(
                item.net_qty_per_portion,
                ingredient.waste_factor,
                ingredient.cooking_yield_factor,
            )
    elif item.sub_recipe_id is not None:
        label = recipe_names.get(item.sub_recipe_id, "Sub-receta")
    else:
        label = "Sin vínculo"
    return RecipeItemRead(
        id=item.id,
        ingredient_id=item.ingredient_id,
        sub_recipe_id=item.sub_recipe_id,
        label=label,
        unit=unit,
        net_qty_per_portion=item.net_qty_per_portion,
        gross_qty=gross,
    )


def _group_read(
    group: PackageRecipeGroup,
    options_by_group: dict[UUID, list[PackageGroupOption]],
    recipe_names: dict[UUID, str],
) -> PackageGroupRead:
    options = options_by_group.get(group.id, [])
    options.sort(key=lambda row: recipe_names.get(row.recipe_id, "").lower())
    return PackageGroupRead(
        id=group.id,
        group_name=group.group_name,
        min_choices=group.min_choices,
        max_choices=group.max_choices,
        is_fixed=group.is_fixed,
        options=[
            PackageOptionRead(
                id=option.id,
                recipe_id=option.recipe_id,
                recipe_name=recipe_names.get(option.recipe_id, "Receta"),
                portions_per_guest=option.portions_per_guest,
                extra_price_per_guest=option.extra_price_per_guest,
            )
            for option in options
        ],
    )


def _extra_read(
    row: MenuExtra,
    ingredients: dict[UUID, str],
    recipes: dict[UUID, str],
    links: dict[UUID, list[UUID]] | None = None,
    category_names: dict[UUID, str] | None = None,
) -> ExtraRead:
    if row.ingredient_id is not None:
        label = ingredients.get(row.ingredient_id, "Insumo")
    elif row.recipe_id is not None:
        label = recipes.get(row.recipe_id, "Receta")
    else:
        label = "Sin vínculo"
    category_ids = (links or {}).get(row.id, [])
    names = category_names or {}
    return ExtraRead(
        id=row.id,
        name=row.name,
        ingredient_id=row.ingredient_id,
        recipe_id=row.recipe_id,
        link_label=label,
        unit_price=row.unit_price,
        pricing_type=row.pricing_type,
        is_active=row.is_active,
        category_ids=category_ids,
        category_names=[names.get(item, "Categoría") for item in category_ids],
    )


async def _extra_category_map(
    session: AsyncSession, tenant_id: UUID
) -> dict[UUID, list[UUID]]:
    result = await session.exec(
        select(ExtraCategory).where(ExtraCategory.tenant_id == tenant_id)
    )
    grouped: dict[UUID, list[UUID]] = {}
    for row in result.all():
        grouped.setdefault(row.extra_id, []).append(row.category_id)
    return grouped


async def _links_for_extra(
    session: AsyncSession, tenant_id: UUID, extra_id: UUID
) -> list[ExtraCategory]:
    result = await session.exec(
        select(ExtraCategory).where(ExtraCategory.tenant_id == tenant_id)
    )
    return [row for row in result.all() if row.extra_id == extra_id]


async def _replace_extra_categories(
    session: AsyncSession,
    tenant_id: UUID,
    extra_id: UUID,
    category_ids: list[UUID],
) -> None:
    for link in await _links_for_extra(session, tenant_id, extra_id):
        await session.delete(link)
    await session.flush()
    seen: set[UUID] = set()
    for category_id in category_ids:
        if category_id in seen:
            continue
        seen.add(category_id)
        await _require_category(session, category_id)
        session.add(
            ExtraCategory(
                tenant_id=tenant_id,
                extra_id=extra_id,
                category_id=category_id,
            )
        )
    await session.flush()


def _portion_cost(
    recipe_id: UUID,
    recipes: dict[UUID, RecipeCost],
    ingredients: dict[UUID, IngredientCost],
) -> tuple[Decimal | None, str | None]:
    try:
        return recipe_cost(recipe_id, recipes, ingredients, portions=1), None
    except CostError as exc:
        return None, str(exc)


def _engine_maps(
    recipes: list[Recipe],
    items: list[RecipeItem],
    ingredients: list[Ingredient],
) -> tuple[dict[UUID, RecipeCost], dict[UUID, IngredientCost]]:
    grouped: dict[UUID, list[RecipeLine]] = {}
    for item in items:
        grouped.setdefault(item.recipe_id, []).append(
            RecipeLine(
                ingredient_id=item.ingredient_id,
                sub_recipe_id=item.sub_recipe_id,
                net_qty_per_portion=item.net_qty_per_portion,
            )
        )
    nodes = {
        recipe.id: RecipeCost(
            id=recipe.id,
            portion_size=recipe.portion_size,
            lines=tuple(grouped.get(recipe.id, [])),
        )
        for recipe in recipes
    }
    costs = {
        ingredient.id: IngredientCost(
            id=ingredient.id,
            purchase_price=ingredient.purchase_price,
            waste_factor=ingredient.waste_factor,
            cooking_yield_factor=ingredient.cooking_yield_factor,
        )
        for ingredient in ingredients
    }
    return nodes, costs


async def _line_targets(
    session: AsyncSession,
    tenant_id: UUID,
    recipe_id: UUID,
    ingredient_id: UUID | None,
    sub_recipe_id: UUID | None,
) -> tuple[UUID | None, UUID | None]:
    if (ingredient_id is None) == (sub_recipe_id is None):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="La línea apunta a un insumo o a una sub-receta",
        )
    if ingredient_id is not None:
        await owned(
            session, Ingredient, ingredient_id, tenant_id, "No se encontró el insumo"
        )
        return ingredient_id, None
    if sub_recipe_id == recipe_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Una receta no puede contenerse a sí misma",
        )
    assert sub_recipe_id is not None
    await owned(
        session, Recipe, sub_recipe_id, tenant_id, "No se encontró la sub-receta"
    )
    return None, sub_recipe_id


async def _extra_links(
    session: AsyncSession,
    tenant_id: UUID,
    ingredient_id: UUID | None,
    recipe_id: UUID | None,
) -> tuple[UUID | None, UUID | None]:
    if ingredient_id is not None and recipe_id is not None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="El extra no puede tener insumo y receta a la vez",
        )
    if ingredient_id is not None:
        await owned(
            session, Ingredient, ingredient_id, tenant_id, "No se encontró el insumo"
        )
    if recipe_id is not None:
        await owned(session, Recipe, recipe_id, tenant_id, "No se encontró la receta")
    return ingredient_id, recipe_id


def _portion_unit(value: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Indica la unidad de la porción",
        )
    if len(cleaned) > 20:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="La unidad de la porción es demasiado larga",
        )
    return cleaned


def _min_guests(value: int) -> int:
    if value < 1:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="El mínimo de invitados debe ser al menos 1",
        )
    return value


def _check_choices(min_choices: int, max_choices: int, is_fixed: bool) -> None:
    if min_choices < 0 or max_choices < 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Las opciones del grupo no pueden ser negativas",
        )
    if max_choices < min_choices:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="El máximo de opciones no puede ser menor que el mínimo",
        )
    if not is_fixed and max_choices < 1:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="El grupo debe permitir al menos una opción",
        )


async def _require_category(session: AsyncSession, category_id: UUID) -> None:
    category = await session.get(ServiceCategory, category_id)
    if category is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Elige una categoría de servicio válida",
        )


async def list_service_categories(session: AsyncSession) -> list[CategoryRead]:
    rows = [row for row in await _category_rows(session) if row.is_active]
    rows.sort(key=lambda row: row.name.lower())
    return [CategoryRead(id=row.id, name=row.name, slug=row.slug) for row in rows]


async def _categories(session: AsyncSession) -> list[CategoryRead]:
    return await list_service_categories(session)


async def _category_rows(session: AsyncSession) -> list[ServiceCategory]:
    result = await session.exec(select(ServiceCategory))
    return list(result.all())


async def _recipes(session: AsyncSession, tenant_id: UUID) -> list[Recipe]:
    result = await session.exec(select(Recipe).where(Recipe.tenant_id == tenant_id))
    rows = list(result.all())
    rows.sort(key=lambda row: row.name.lower())
    return rows


async def _items(session: AsyncSession, tenant_id: UUID) -> list[RecipeItem]:
    result = await session.exec(
        select(RecipeItem).where(RecipeItem.tenant_id == tenant_id)
    )
    return list(result.all())


async def _items_of(
    session: AsyncSession, tenant_id: UUID, recipe_id: UUID
) -> list[RecipeItem]:
    result = await session.exec(
        select(RecipeItem).where(
            RecipeItem.tenant_id == tenant_id,
            RecipeItem.recipe_id == recipe_id,
        )
    )
    return list(result.all())


async def _sub_recipe_uses(
    session: AsyncSession, tenant_id: UUID, recipe_id: UUID
) -> list[RecipeItem]:
    result = await session.exec(
        select(RecipeItem).where(
            RecipeItem.tenant_id == tenant_id,
            RecipeItem.sub_recipe_id == recipe_id,
        )
    )
    return list(result.all())


async def _option_uses(
    session: AsyncSession, tenant_id: UUID, recipe_id: UUID
) -> list[PackageGroupOption]:
    result = await session.exec(
        select(PackageGroupOption).where(
            PackageGroupOption.tenant_id == tenant_id,
            PackageGroupOption.recipe_id == recipe_id,
        )
    )
    return list(result.all())


async def _extra_recipe_uses(
    session: AsyncSession, tenant_id: UUID, recipe_id: UUID
) -> list[MenuExtra]:
    result = await session.exec(
        select(MenuExtra).where(
            MenuExtra.tenant_id == tenant_id,
            MenuExtra.recipe_id == recipe_id,
        )
    )
    return list(result.all())


async def _packages(session: AsyncSession, tenant_id: UUID) -> list[CateringPackage]:
    result = await session.exec(
        select(CateringPackage).where(CateringPackage.tenant_id == tenant_id)
    )
    rows = list(result.all())
    rows.sort(key=lambda row: row.name.lower())
    return rows


async def _groups(session: AsyncSession, tenant_id: UUID) -> list[PackageRecipeGroup]:
    result = await session.exec(
        select(PackageRecipeGroup).where(PackageRecipeGroup.tenant_id == tenant_id)
    )
    return list(result.all())


async def _groups_of(
    session: AsyncSession, tenant_id: UUID, package_id: UUID
) -> list[PackageRecipeGroup]:
    result = await session.exec(
        select(PackageRecipeGroup).where(
            PackageRecipeGroup.tenant_id == tenant_id,
            PackageRecipeGroup.package_id == package_id,
        )
    )
    return list(result.all())


async def _options(session: AsyncSession, tenant_id: UUID) -> list[PackageGroupOption]:
    result = await session.exec(
        select(PackageGroupOption).where(PackageGroupOption.tenant_id == tenant_id)
    )
    return list(result.all())


async def _extra_rows(session: AsyncSession, tenant_id: UUID) -> list[MenuExtra]:
    result = await session.exec(
        select(MenuExtra).where(MenuExtra.tenant_id == tenant_id)
    )
    rows = list(result.all())
    rows.sort(key=lambda row: row.name.lower())
    return rows


async def _ingredient_rows(session: AsyncSession, tenant_id: UUID) -> list[Ingredient]:
    result = await session.exec(
        select(Ingredient).where(Ingredient.tenant_id == tenant_id)
    )
    return list(result.all())
