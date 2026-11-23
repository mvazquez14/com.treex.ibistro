from collections.abc import Awaitable, Callable
from uuid import UUID

from fastapi import APIRouter, Form, HTTPException, Request
from starlette.responses import Response

from app.api.deps import CurrentActiveTenant, SessionDep
from app.api.forms import (
    checked,
    decimal_field,
    float_field,
    int_field,
    optional_uuid,
)
from app.models.enums import PricingType
from app.schemas.catalog import (
    ExtraIn,
    ExtraUpdate,
    PackageGroupIn,
    PackageGroupUpdate,
    PackageIn,
    PackageOptionIn,
    PackageUpdate,
    QuoteExtraIn,
    QuoteIn,
    QuoteRead,
    RecipeIn,
    RecipeItemIn,
    RecipeUpdate,
)
from app.services import menu_catalog
from app.services.catalog_common import as_enum
from app.templating import failure, render

router = APIRouter(prefix="/menu", tags=["dashboard"])


async def _render(
    request: Request,
    session: SessionDep,
    tenant_id: UUID,
    error: str | None = None,
    status_code: int = 200,
    quote: QuoteRead | None = None,
    quote_package_id: UUID | None = None,
) -> Response:
    snapshot = await menu_catalog.menu_snapshot(session, tenant_id)
    return render(
        request,
        "dashboard/menu.html",
        "dashboard/menu_panel.html",
        {
            "section": "menu",
            "snapshot": snapshot,
            "error": error,
            "quote": quote,
            "quote_package_id": quote_package_id,
        },
        status_code,
    )


async def _run(
    request: Request,
    session: SessionDep,
    tenant: CurrentActiveTenant,
    action: Callable[[], Awaitable[object]],
) -> Response:
    tenant_id = tenant.id
    quote: QuoteRead | None = None
    quote_package_id: UUID | None = None
    try:
        outcome = await action()
        await session.commit()
        if isinstance(outcome, tuple):
            quote, quote_package_id = outcome
    except HTTPException as exc:
        await session.rollback()
        message, code = failure(exc)
        return await _render(request, session, tenant_id, message, code)
    return await _render(
        request,
        session,
        tenant_id,
        quote=quote,
        quote_package_id=quote_package_id,
    )


@router.get("")
async def menu_page(
    request: Request, session: SessionDep, tenant: CurrentActiveTenant
) -> Response:
    return await _render(request, session, tenant.id)


@router.post("/recipes")
async def create_recipe(
    request: Request,
    session: SessionDep,
    tenant: CurrentActiveTenant,
    name: str = Form(),
    portion_size: str = Form(),
    portion_unit: str = Form(),
    is_sub_recipe: str | None = Form(default=None),
) -> Response:
    async def action() -> None:
        await menu_catalog.create_recipe(
            session,
            tenant.id,
            RecipeIn(
                name=name,
                portion_size=float_field(portion_size, "El tamaño de porción"),
                portion_unit=portion_unit,
                is_sub_recipe=checked(is_sub_recipe),
            ),
        )

    return await _run(request, session, tenant, action)


@router.post("/recipes/{recipe_id}")
async def update_recipe(
    request: Request,
    session: SessionDep,
    tenant: CurrentActiveTenant,
    recipe_id: UUID,
    name: str = Form(),
    portion_size: str = Form(),
    portion_unit: str = Form(),
    is_sub_recipe: str | None = Form(default=None),
) -> Response:
    async def action() -> None:
        await menu_catalog.update_recipe(
            session,
            tenant.id,
            recipe_id,
            RecipeUpdate(
                name=name,
                portion_size=float_field(portion_size, "El tamaño de porción"),
                portion_unit=portion_unit,
                is_sub_recipe=checked(is_sub_recipe),
            ),
        )

    return await _run(request, session, tenant, action)


@router.post("/recipes/{recipe_id}/delete")
async def remove_recipe(
    request: Request,
    session: SessionDep,
    tenant: CurrentActiveTenant,
    recipe_id: UUID,
) -> Response:
    async def action() -> None:
        await menu_catalog.delete_recipe(session, tenant.id, recipe_id)

    return await _run(request, session, tenant, action)


@router.post("/recipes/{recipe_id}/items")
async def create_item(
    request: Request,
    session: SessionDep,
    tenant: CurrentActiveTenant,
    recipe_id: UUID,
    net_qty_per_portion: str = Form(),
    ingredient_id: str = Form(default=""),
    sub_recipe_id: str = Form(default=""),
) -> Response:
    async def action() -> None:
        await menu_catalog.add_recipe_item(
            session,
            tenant.id,
            recipe_id,
            RecipeItemIn(
                ingredient_id=optional_uuid(ingredient_id),
                sub_recipe_id=optional_uuid(sub_recipe_id),
                net_qty_per_portion=float_field(
                    net_qty_per_portion, "La cantidad neta"
                ),
            ),
        )

    return await _run(request, session, tenant, action)


@router.post("/recipe-items/{item_id}/delete")
async def remove_item(
    request: Request,
    session: SessionDep,
    tenant: CurrentActiveTenant,
    item_id: UUID,
) -> Response:
    async def action() -> None:
        await menu_catalog.delete_recipe_item(session, tenant.id, item_id)

    return await _run(request, session, tenant, action)


@router.post("/packages")
async def create_package(
    request: Request,
    session: SessionDep,
    tenant: CurrentActiveTenant,
    name: str = Form(),
    category_id: str = Form(),
    description: str = Form(default=""),
    photo_url: str = Form(default=""),
    base_price_per_guest: str = Form(),
    min_guests: str = Form(),
    is_active: str | None = Form(default=None),
) -> Response:
    async def action() -> None:
        category = optional_uuid(category_id)
        if category is None:
            raise HTTPException(
                status_code=422, detail="Elige una categoría de servicio"
            )
        await menu_catalog.create_package(
            session,
            tenant.id,
            PackageIn(
                category_id=category,
                name=name,
                description=description,
                photo_url=photo_url or None,
                base_price_per_guest=decimal_field(
                    base_price_per_guest, "El precio base"
                ),
                min_guests=int_field(min_guests, "El mínimo de invitados"),
                is_active=is_active != "false",
            ),
        )

    return await _run(request, session, tenant, action)


@router.post("/packages/{package_id}")
async def update_package(
    request: Request,
    session: SessionDep,
    tenant: CurrentActiveTenant,
    package_id: UUID,
    name: str = Form(),
    category_id: str = Form(),
    description: str = Form(default=""),
    photo_url: str = Form(default=""),
    base_price_per_guest: str = Form(),
    min_guests: str = Form(),
    is_active: str | None = Form(default=None),
) -> Response:
    async def action() -> None:
        category = optional_uuid(category_id)
        if category is None:
            raise HTTPException(
                status_code=422, detail="Elige una categoría de servicio"
            )
        await menu_catalog.update_package(
            session,
            tenant.id,
            package_id,
            PackageUpdate(
                category_id=category,
                name=name,
                description=description,
                photo_url=photo_url or None,
                base_price_per_guest=decimal_field(
                    base_price_per_guest, "El precio base"
                ),
                min_guests=int_field(min_guests, "El mínimo de invitados"),
                is_active=checked(is_active),
            ),
        )

    return await _run(request, session, tenant, action)


@router.post("/packages/{package_id}/delete")
async def remove_package(
    request: Request,
    session: SessionDep,
    tenant: CurrentActiveTenant,
    package_id: UUID,
) -> Response:
    async def action() -> None:
        await menu_catalog.delete_package(session, tenant.id, package_id)

    return await _run(request, session, tenant, action)


@router.post("/packages/{package_id}/groups")
async def create_group(
    request: Request,
    session: SessionDep,
    tenant: CurrentActiveTenant,
    package_id: UUID,
    group_name: str = Form(),
    min_choices: str = Form(default="1"),
    max_choices: str = Form(default="1"),
    is_fixed: str | None = Form(default=None),
) -> Response:
    async def action() -> None:
        await menu_catalog.add_group(
            session,
            tenant.id,
            package_id,
            PackageGroupIn(
                group_name=group_name,
                min_choices=int_field(min_choices, "El mínimo de opciones"),
                max_choices=int_field(max_choices, "El máximo de opciones"),
                is_fixed=checked(is_fixed),
            ),
        )

    return await _run(request, session, tenant, action)


@router.post("/groups/{group_id}")
async def update_group(
    request: Request,
    session: SessionDep,
    tenant: CurrentActiveTenant,
    group_id: UUID,
    group_name: str = Form(),
    min_choices: str = Form(),
    max_choices: str = Form(),
    is_fixed: str | None = Form(default=None),
) -> Response:
    async def action() -> None:
        await menu_catalog.update_group(
            session,
            tenant.id,
            group_id,
            PackageGroupUpdate(
                group_name=group_name,
                min_choices=int_field(min_choices, "El mínimo de opciones"),
                max_choices=int_field(max_choices, "El máximo de opciones"),
                is_fixed=checked(is_fixed),
            ),
        )

    return await _run(request, session, tenant, action)


@router.post("/groups/{group_id}/delete")
async def remove_group(
    request: Request,
    session: SessionDep,
    tenant: CurrentActiveTenant,
    group_id: UUID,
) -> Response:
    async def action() -> None:
        await menu_catalog.delete_group(session, tenant.id, group_id)

    return await _run(request, session, tenant, action)


@router.post("/groups/{group_id}/options")
async def create_option(
    request: Request,
    session: SessionDep,
    tenant: CurrentActiveTenant,
    group_id: UUID,
    recipe_id: str = Form(),
    portions_per_guest: str = Form(default="1"),
    extra_price_per_guest: str = Form(default="0"),
) -> Response:
    async def action() -> None:
        recipe = optional_uuid(recipe_id)
        if recipe is None:
            raise HTTPException(status_code=422, detail="Elige una receta")
        await menu_catalog.add_option(
            session,
            tenant.id,
            group_id,
            PackageOptionIn(
                recipe_id=recipe,
                portions_per_guest=float_field(
                    portions_per_guest, "Las porciones por invitado"
                ),
                extra_price_per_guest=decimal_field(
                    extra_price_per_guest, "El precio extra"
                ),
            ),
        )

    return await _run(request, session, tenant, action)


@router.post("/options/{option_id}/delete")
async def remove_option(
    request: Request,
    session: SessionDep,
    tenant: CurrentActiveTenant,
    option_id: UUID,
) -> Response:
    async def action() -> None:
        await menu_catalog.delete_option(session, tenant.id, option_id)

    return await _run(request, session, tenant, action)


@router.post("/packages/{package_id}/quote")
async def quote_package(
    request: Request,
    session: SessionDep,
    tenant: CurrentActiveTenant,
    package_id: UUID,
) -> Response:
    form = await request.form()

    async def action() -> tuple[QuoteRead, UUID]:
        selected: dict[UUID, list[UUID]] = {}
        for key, value in form.multi_items():
            if not str(key).startswith("choice_"):
                continue
            group_id = optional_uuid(str(key).removeprefix("choice_"))
            recipe = optional_uuid(str(value))
            if group_id is None or recipe is None:
                raise HTTPException(
                    status_code=422, detail="La selección del paquete no es válida"
                )
            selected.setdefault(group_id, []).append(recipe)
        extras: list[QuoteExtraIn] = []
        extra_id = optional_uuid(str(form.get("extra_id") or ""))
        if extra_id is not None:
            quantity = str(form.get("extra_quantity") or "1")
            extras.append(
                QuoteExtraIn(
                    extra_id=extra_id,
                    quantity=float_field(quantity, "La cantidad del extra"),
                )
            )
        guests = int_field(str(form.get("guest_count") or ""), "Los invitados")
        quote = await menu_catalog.quote_for_package(
            session,
            tenant.id,
            package_id,
            QuoteIn(guest_count=guests, selected_options=selected, extras=extras),
        )
        return quote, package_id

    return await _run(request, session, tenant, action)


@router.post("/extras")
async def create_extra(
    request: Request,
    session: SessionDep,
    tenant: CurrentActiveTenant,
    name: str = Form(),
    unit_price: str = Form(),
    pricing_type: str = Form(),
    ingredient_id: str = Form(default=""),
    recipe_id: str = Form(default=""),
    is_active: str | None = Form(default=None),
) -> Response:
    async def action() -> None:
        await menu_catalog.create_extra(
            session,
            tenant.id,
            ExtraIn(
                name=name,
                unit_price=decimal_field(unit_price, "El precio"),
                pricing_type=_pricing(pricing_type),
                ingredient_id=optional_uuid(ingredient_id),
                recipe_id=optional_uuid(recipe_id),
                is_active=is_active != "false",
            ),
        )

    return await _run(request, session, tenant, action)


@router.post("/extras/{extra_id}")
async def update_extra(
    request: Request,
    session: SessionDep,
    tenant: CurrentActiveTenant,
    extra_id: UUID,
    name: str = Form(),
    unit_price: str = Form(),
    pricing_type: str = Form(),
    ingredient_id: str = Form(default=""),
    recipe_id: str = Form(default=""),
    is_active: str | None = Form(default=None),
) -> Response:
    async def action() -> None:
        ingredient = optional_uuid(ingredient_id)
        recipe = optional_uuid(recipe_id)
        await menu_catalog.update_extra(
            session,
            tenant.id,
            extra_id,
            ExtraUpdate(
                name=name,
                unit_price=decimal_field(unit_price, "El precio"),
                pricing_type=_pricing(pricing_type),
                ingredient_id=ingredient,
                recipe_id=recipe,
                clear_ingredient=ingredient is None,
                clear_recipe=recipe is None,
                is_active=checked(is_active),
            ),
        )

    return await _run(request, session, tenant, action)


@router.post("/extras/{extra_id}/delete")
async def remove_extra(
    request: Request,
    session: SessionDep,
    tenant: CurrentActiveTenant,
    extra_id: UUID,
) -> Response:
    async def action() -> None:
        await menu_catalog.delete_extra(session, tenant.id, extra_id)

    return await _run(request, session, tenant, action)


def _pricing(value: str) -> PricingType:
    return as_enum(PricingType, value, "El tipo de cobro no es válido")
