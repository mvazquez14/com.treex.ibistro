from collections.abc import Awaitable, Callable

from fastapi import APIRouter, Form, HTTPException, Request
from starlette.responses import Response

from app.api.deps import CurrentActiveTenant, SessionDep
from app.api.forms import decimal_field, int_field, optional_uuid
from app.schemas.catalog import AssetIn, AssetUpdate, RuleIn, RuleUpdate
from app.services import equipment_catalog as catalog
from app.templating import failure, render

router = APIRouter(prefix="/equipment", tags=["dashboard"])


async def _render(
    request: Request,
    session: SessionDep,
    tenant: CurrentActiveTenant,
    guests: int,
    error: str | None = None,
    status_code: int = 200,
) -> Response:
    try:
        snapshot = await catalog.equipment_snapshot(session, tenant.id, guests=guests)
    except HTTPException as exc:
        message, code = failure(exc)
        snapshot = await catalog.equipment_snapshot(session, tenant.id, guests=0)
        error = message if error is None else error
        status_code = code
    return render(
        request,
        "dashboard/equipment.html",
        "dashboard/equipment_panel.html",
        {"section": "equipment", "snapshot": snapshot, "error": error},
        status_code,
    )


async def _run(
    request: Request,
    session: SessionDep,
    tenant: CurrentActiveTenant,
    guests: int,
    action: Callable[[], Awaitable[None]],
) -> Response:
    try:
        await action()
        await session.commit()
    except HTTPException as exc:
        await session.rollback()
        message, code = failure(exc)
        return await _render(request, session, tenant, guests, message, code)
    return await _render(request, session, tenant, guests)


@router.get("")
async def equipment_page(
    request: Request,
    session: SessionDep,
    tenant: CurrentActiveTenant,
    guests: int = 25,
) -> Response:
    return await _render(request, session, tenant, guests)


@router.post("/assets")
async def create_asset(
    request: Request,
    session: SessionDep,
    tenant: CurrentActiveTenant,
    name: str = Form(),
    category: str = Form(),
    total_stock: str = Form(),
    rental_price_per_unit: str = Form(default="0"),
    replacement_cost: str = Form(),
    guests: int = 25,
) -> Response:
    async def action() -> None:
        await catalog.create_asset(
            session,
            tenant.id,
            AssetIn(
                name=name,
                category=catalog.parse_category(category),
                total_stock=int_field(total_stock, "La existencia"),
                rental_price_per_unit=decimal_field(rental_price_per_unit, "La renta"),
                replacement_cost=decimal_field(
                    replacement_cost, "El costo de reposición"
                ),
            ),
        )

    return await _run(request, session, tenant, guests, action)


@router.post("/assets/{asset_id}")
async def update_asset(
    request: Request,
    session: SessionDep,
    tenant: CurrentActiveTenant,
    asset_id: str,
    name: str = Form(),
    category: str = Form(),
    total_stock: str = Form(),
    rental_price_per_unit: str = Form(default="0"),
    replacement_cost: str = Form(),
    guests: int = 25,
) -> Response:
    async def action() -> None:
        parsed = optional_uuid(asset_id)
        if parsed is None:
            raise HTTPException(status_code=422, detail="No se encontró el equipo")
        await catalog.update_asset(
            session,
            tenant.id,
            parsed,
            AssetUpdate(
                name=name,
                category=catalog.parse_category(category),
                total_stock=int_field(total_stock, "La existencia"),
                rental_price_per_unit=decimal_field(rental_price_per_unit, "La renta"),
                replacement_cost=decimal_field(
                    replacement_cost, "El costo de reposición"
                ),
            ),
        )

    return await _run(request, session, tenant, guests, action)


@router.post("/assets/{asset_id}/delete")
async def remove_asset(
    request: Request,
    session: SessionDep,
    tenant: CurrentActiveTenant,
    asset_id: str,
    guests: int = 25,
) -> Response:
    async def action() -> None:
        parsed = optional_uuid(asset_id)
        if parsed is None:
            raise HTTPException(status_code=422, detail="No se encontró el equipo")
        await catalog.delete_asset(session, tenant.id, parsed)

    return await _run(request, session, tenant, guests, action)


@router.post("/rules")
async def create_rule(
    request: Request,
    session: SessionDep,
    tenant: CurrentActiveTenant,
    package_id: str = Form(),
    asset_id: str = Form(),
    guests_per_unit: str = Form(),
    guests: int = 25,
) -> Response:
    async def action() -> None:
        package = optional_uuid(package_id)
        asset = optional_uuid(asset_id)
        if package is None or asset is None:
            raise HTTPException(status_code=422, detail="Elige el paquete y el equipo")
        await catalog.create_rule(
            session,
            tenant.id,
            RuleIn(
                package_id=package,
                asset_id=asset,
                guests_per_unit=int_field(guests_per_unit, "Los invitados por unidad"),
            ),
            guests=guests,
        )

    return await _run(request, session, tenant, guests, action)


@router.post("/rules/{rule_id}")
async def update_rule(
    request: Request,
    session: SessionDep,
    tenant: CurrentActiveTenant,
    rule_id: str,
    guests_per_unit: str = Form(),
    guests: int = 25,
) -> Response:
    async def action() -> None:
        parsed = optional_uuid(rule_id)
        if parsed is None:
            raise HTTPException(status_code=422, detail="No se encontró la regla")
        await catalog.update_rule(
            session,
            tenant.id,
            parsed,
            RuleUpdate(
                guests_per_unit=int_field(guests_per_unit, "Los invitados por unidad")
            ),
            guests=guests,
        )

    return await _run(request, session, tenant, guests, action)


@router.post("/rules/{rule_id}/delete")
async def remove_rule(
    request: Request,
    session: SessionDep,
    tenant: CurrentActiveTenant,
    rule_id: str,
    guests: int = 25,
) -> Response:
    async def action() -> None:
        parsed = optional_uuid(rule_id)
        if parsed is None:
            raise HTTPException(status_code=422, detail="No se encontró la regla")
        await catalog.delete_rule(session, tenant.id, parsed)

    return await _run(request, session, tenant, guests, action)
