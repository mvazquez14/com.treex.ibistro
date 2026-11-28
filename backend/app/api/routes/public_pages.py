"""HTML micro-landing at /c/{slug}."""

from datetime import date
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request, status
from starlette.datastructures import FormData
from starlette.responses import Response

from app.api.deps import SessionDep
from app.api.forms import float_field, int_field, optional_uuid
from app.schemas.catalog import QuoteExtraIn
from app.schemas.quotes import MonthAvailability, PublicQuoteIn
from app.services import quoting
from app.templating import failure, templates

router = APIRouter(tags=["public"])


def _event_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="La fecha no es válida",
        )


def _text(form: FormData, name: str) -> str:
    value = form.get(name)
    return value.strip() if isinstance(value, str) else ""


def _texts(form: FormData, name: str) -> list[str]:
    return [item.strip() for item in form.getlist(name) if isinstance(item, str)]


async def _quote_form(request: Request) -> PublicQuoteIn:
    form = await request.form()
    package_id = optional_uuid(_text(form, "package_id"))
    booking = _text(form, "booking")
    slot_raw, _sep, start_raw = booking.partition("|")
    slot_id = optional_uuid(slot_raw) or optional_uuid(_text(form, "slot_id"))
    start_time = start_raw or _text(form, "start_time") or None
    if package_id is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Elige un paquete",
        )
    if slot_id is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Elige un horario",
        )
    selected: dict[UUID, list[UUID]] = {}
    for raw in _texts(form, "choice"):
        group_raw, sep, rest = raw.partition(":")
        if not sep:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="La variante no es válida",
            )
        recipe_raw, qty_sep, qty_raw = rest.partition(":")
        group_id = optional_uuid(group_raw)
        recipe_id = optional_uuid(recipe_raw)
        if group_id is None or recipe_id is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="La variante no es válida",
            )
        if qty_sep:
            try:
                quantity = int(qty_raw)
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail="La variante no es válida",
                )
        else:
            quantity = 1
        if quantity < 1:
            continue
        selected.setdefault(group_id, []).extend([recipe_id] * quantity)
    extras: list[QuoteExtraIn] = []
    for raw in _texts(form, "extra"):
        extra_id = optional_uuid(raw)
        if extra_id is None:
            continue
        quantity_text = _text(form, f"extra_qty_{extra_id}") or "1"
        extras.append(
            QuoteExtraIn(
                extra_id=extra_id,
                quantity=float_field(quantity_text, "La cantidad"),
            )
        )
    return PublicQuoteIn(
        package_id=package_id,
        event_date=_event_date(_text(form, "event_date")),
        slot_id=slot_id,
        guest_count=int_field(_text(form, "guest_count"), "Los invitados"),
        full_name=_text(form, "full_name"),
        phone=_text(form, "phone"),
        whatsapp_phone=_text(form, "whatsapp_phone"),
        email=_text(form, "email") or None,
        venue_address=_text(form, "venue_address"),
        special_requests=_text(form, "special_requests") or None,
        selected_options=selected,
        extras=extras,
        delivery_zone_id=optional_uuid(_text(form, "delivery_zone_id")),
        start_time=start_time,
    )


def _error(request: Request, exc: HTTPException) -> Response:
    message, code = failure(exc)
    return templates.TemplateResponse(
        request,
        "public/error.html",
        {"message": message},
        status_code=code,
    )


@router.get("/c/{slug}/availability", response_model=MonthAvailability)
async def availability(
    session: SessionDep,
    slug: str,
    month: str = Query(min_length=7, max_length=7),
) -> MonthAvailability:
    return await quoting.public_month(session, slug, month)


@router.get("/c/{slug}")
async def landing(request: Request, session: SessionDep, slug: str) -> Response:
    try:
        page = await quoting.landing_page(session, slug)
    except HTTPException as exc:
        return _error(request, exc)
    return templates.TemplateResponse(request, "public/landing.html", {"page": page})


@router.post("/c/{slug}/preview")
async def preview(request: Request, session: SessionDep, slug: str) -> Response:
    try:
        data = await _quote_form(request)
        priced = await quoting.preview_public_quote(session, slug, data)
    except HTTPException as exc:
        message, code = failure(exc)
        return templates.TemplateResponse(
            request,
            "public/preview.html",
            {"preview": None, "error": message},
            status_code=code,
        )
    return templates.TemplateResponse(
        request,
        "public/preview.html",
        {"preview": priced, "error": None},
    )


@router.post("/c/{slug}/quotes")
async def send_quote(request: Request, session: SessionDep, slug: str) -> Response:
    try:
        data = await _quote_form(request)
        created = await quoting.submit_public_quote(session, slug, data)
        await session.commit()
    except HTTPException as exc:
        await session.rollback()
        return _error(request, exc)
    return templates.TemplateResponse(
        request,
        "public/result.html",
        {"page": created, "business_name": data.full_name},
        status_code=status.HTTP_201_CREATED,
    )
