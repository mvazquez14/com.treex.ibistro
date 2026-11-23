"""HTMX quotes desk: discounts, IVA, PDF, and reservation."""

from uuid import UUID

from fastapi import APIRouter, Form, HTTPException, Request
from starlette.responses import Response

from app.api.deps import CurrentActiveTenant, SessionDep
from app.api.forms import checked, decimal_field, int_field
from app.schemas.quotes import PhotoIn, QuoteAdjustIn, SlotIn, ZoneIn
from app.services import quoting
from app.services import schedule_catalog as catalog
from app.templating import failure, render

router = APIRouter(prefix="/quotes", tags=["dashboard"])


async def _render(
    request: Request,
    session: SessionDep,
    tenant: CurrentActiveTenant,
    error: str | None = None,
    status_code: int = 200,
) -> Response:
    screen = await quoting.quotes_screen(session, tenant)
    return render(
        request,
        "dashboard/quotes.html",
        "dashboard/quotes_panel.html",
        {"section": "quotes", "screen": screen, "error": error},
        status_code,
    )


@router.get("")
async def quotes_page(
    request: Request, session: SessionDep, tenant: CurrentActiveTenant
) -> Response:
    return await _render(request, session, tenant)


@router.post("/slots")
async def create_slot(
    request: Request,
    session: SessionDep,
    tenant: CurrentActiveTenant,
    day_of_week: str = Form(),
    start_time: str = Form(),
    end_time: str = Form(),
    is_active: str = Form(default="true"),
) -> Response:
    try:
        await catalog.create_slot(
            session,
            tenant.id,
            SlotIn(
                day_of_week=int_field(day_of_week, "El día"),
                start_time=start_time,
                end_time=end_time,
                is_active=is_active == "true",
            ),
        )
        await session.commit()
    except HTTPException as exc:
        await session.rollback()
        message, code = failure(exc)
        return await _render(request, session, tenant, message, code)
    return await _render(request, session, tenant)


@router.post("/slots/{slot_id}/delete")
async def delete_slot(
    request: Request,
    session: SessionDep,
    tenant: CurrentActiveTenant,
    slot_id: UUID,
) -> Response:
    try:
        await catalog.delete_slot(session, tenant.id, slot_id)
        await session.commit()
    except HTTPException as exc:
        await session.rollback()
        message, code = failure(exc)
        return await _render(request, session, tenant, message, code)
    return await _render(request, session, tenant)


@router.post("/photos")
async def create_photo(
    request: Request,
    session: SessionDep,
    tenant: CurrentActiveTenant,
    image_url: str = Form(),
    caption: str = Form(default=""),
    display_order: str = Form(default="0"),
) -> Response:
    try:
        await catalog.create_photo(
            session,
            tenant.id,
            PhotoIn(
                image_url=image_url,
                caption=caption or None,
                display_order=int_field(display_order, "El orden"),
            ),
        )
        await session.commit()
    except HTTPException as exc:
        await session.rollback()
        message, code = failure(exc)
        return await _render(request, session, tenant, message, code)
    return await _render(request, session, tenant)


@router.post("/photos/{photo_id}/delete")
async def delete_photo(
    request: Request,
    session: SessionDep,
    tenant: CurrentActiveTenant,
    photo_id: UUID,
) -> Response:
    try:
        await catalog.delete_photo(session, tenant.id, photo_id)
        await session.commit()
    except HTTPException as exc:
        await session.rollback()
        message, code = failure(exc)
        return await _render(request, session, tenant, message, code)
    return await _render(request, session, tenant)


@router.post("/zones")
async def create_zone(
    request: Request,
    session: SessionDep,
    tenant: CurrentActiveTenant,
    zone_name: str = Form(),
    freight_cost: str = Form(),
) -> Response:
    try:
        await catalog.create_zone(
            session,
            tenant.id,
            ZoneIn(
                zone_name=zone_name,
                freight_cost=decimal_field(freight_cost, "El flete"),
            ),
        )
        await session.commit()
    except HTTPException as exc:
        await session.rollback()
        message, code = failure(exc)
        return await _render(request, session, tenant, message, code)
    return await _render(request, session, tenant)


@router.post("/{quote_id}/adjust")
async def adjust_quote(
    request: Request,
    session: SessionDep,
    tenant: CurrentActiveTenant,
    quote_id: UUID,
    discount_amount: str = Form(default="0"),
    tax_rate: str = Form(default=""),
    apply_tax: str | None = Form(default=None),
) -> Response:
    try:
        await quoting.adjust_quote(
            session,
            tenant,
            quote_id,
            QuoteAdjustIn(
                discount_amount=decimal_field(discount_amount, "El descuento"),
                apply_tax=checked(apply_tax),
                tax_rate=decimal_field(tax_rate, "La tasa de IVA")
                if tax_rate.strip()
                else None,
            ),
        )
        await session.commit()
    except HTTPException as exc:
        await session.rollback()
        message, code = failure(exc)
        return await _render(request, session, tenant, message, code)
    return await _render(request, session, tenant)


@router.get("/{quote_id}/pdf")
async def quote_pdf(
    session: SessionDep, tenant: CurrentActiveTenant, quote_id: UUID
) -> Response:
    token, payload = await quoting.quote_pdf(session, tenant, quote_id)
    return Response(
        content=payload,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="cotizacion-{token}.pdf"'
        },
    )


@router.post("/{quote_id}/convert")
async def convert_quote(
    request: Request,
    session: SessionDep,
    tenant: CurrentActiveTenant,
    quote_id: UUID,
) -> Response:
    try:
        await quoting.convert_quote(session, tenant, quote_id)
        await session.commit()
    except HTTPException as exc:
        await session.rollback()
        message, code = failure(exc)
        return await _render(request, session, tenant, message, code)
    return await _render(request, session, tenant)
