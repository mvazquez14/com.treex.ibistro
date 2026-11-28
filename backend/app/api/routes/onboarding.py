"""Three-step onboarding wizard. HTML only; the panel stays a separate app."""

from datetime import time

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from starlette.datastructures import FormData
from starlette.responses import Response

from app.api.deps import SessionDep, get_current_tenant
from app.core.config import settings
from app.core.nuna_auth import organization_from_claims, read_session_claims
from app.models import Tenant
from app.services.impersonation import impersonated_name
from app.services.onboarding_service import (
    complete_onboarding,
    day_labels,
    load_categories,
    preview_slug,
)
from app.templating import templates

router = APIRouter(tags=["onboarding"])


async def _tenant_or_redirect(
    request: Request, session: SessionDep
) -> Tenant | Response:
    claims = read_session_claims(request)
    if not claims:
        return RedirectResponse(url="/login", status_code=302)
    org = organization_from_claims(claims)
    if org["is_superuser"] and impersonated_name(request) is None:
        return RedirectResponse(url="/admin", status_code=302)
    try:
        tenant = await get_current_tenant(request, session)
    except HTTPException:
        return RedirectResponse(url="/login", status_code=302)
    if tenant.onboarding_completed and request.method == "GET":
        return RedirectResponse(url="/dashboard", status_code=302)
    return tenant


@router.get("/onboarding")
async def onboarding_page(request: Request, session: SessionDep) -> Response:
    resolved = await _tenant_or_redirect(request, session)
    if not isinstance(resolved, Tenant):
        return resolved
    return RedirectResponse(url="/dashboard/onboarding", status_code=302)


@router.get("/onboarding/state")
async def onboarding_state(request: Request, session: SessionDep) -> Response:
    resolved = await _tenant_or_redirect(request, session)
    if not isinstance(resolved, Tenant):
        return resolved
    slug, error = await preview_slug(session, resolved, resolved.business_name)
    base = settings.IBISTRO_PUBLIC_BASE_URL.rstrip("/")
    categories = await load_categories(session)
    return JSONResponse(
        {
            "business_name": resolved.business_name,
            "rfc": resolved.rfc,
            "address": resolved.address,
            "min_guests": resolved.min_guests,
            "max_guests": resolved.max_guests,
            "whatsapp_phone": resolved.whatsapp_phone,
            "contact_phone": resolved.contact_phone,
            "show_prices_public": resolved.show_prices_public,
            "max_concurrent_events_per_slot": resolved.max_concurrent_events_per_slot,
            "accepts_cash": resolved.accepts_cash,
            "accepts_transfer": resolved.accepts_transfer,
            "transfer_instructions": resolved.transfer_instructions,
            "categories": [category.name for category in categories],
            "selected_categories": list(resolved.category_tags),
            "days": [{"id": day, "label": label} for day, label in day_labels()],
            "public_base_url": base,
            "slug": slug,
            "slug_error": error or "",
        }
    )


@router.get("/onboarding/slug", response_class=HTMLResponse)
async def onboarding_slug(
    request: Request,
    session: SessionDep,
    business_name: str = "",
    response_format: str = "",
) -> Response:
    resolved = await _tenant_or_redirect(request, session)
    if not isinstance(resolved, Tenant):
        return HTMLResponse("")
    slug, error = await preview_slug(
        session, resolved, business_name or resolved.business_name
    )
    base = settings.IBISTRO_PUBLIC_BASE_URL.rstrip("/")
    if response_format == "json":
        return JSONResponse(
            {"slug": slug, "url": f"{base}/c/{slug}", "error": error or ""}
        )
    if error:
        body = f'<p id="slug-preview" class="text-red-400">{error}</p>'
    else:
        body = (
            f'<p id="slug-preview" class="text-sm text-zinc-400">'
            f"Tu micro-landing: {base}/c/{slug}</p>"
        )
    return HTMLResponse(body)


@router.post("/onboarding/complete")
async def onboarding_complete(
    request: Request,
    session: SessionDep,
    business_name: str = Form(""),
    rfc: str = Form(""),
    address: str = Form(""),
    min_guests: str = Form("20"),
    max_guests: str = Form("300"),
    whatsapp_phone: str = Form(""),
    contact_phone: str = Form(""),
    show_prices_public: str | None = Form(None),
    max_concurrent_events_per_slot: str = Form("1"),
    accepts_cash: str | None = Form(None),
    accepts_transfer: str | None = Form(None),
    transfer_instructions: str = Form(""),
    logo: UploadFile | None = File(None),
) -> Response:
    resolved = await _tenant_or_redirect(request, session)
    if not isinstance(resolved, Tenant):
        return resolved
    tenant = resolved
    if tenant.onboarding_completed:
        return RedirectResponse(url="/dashboard", status_code=302)
    form = await request.form()
    if not isinstance(form, FormData):
        form = FormData(form)
    categories = [item for item in form.getlist("category") if isinstance(item, str)]
    slots: list[tuple[int, time, time]] = []
    posted = _posted(form)
    try:
        for day, _label in day_labels():
            if form.get(f"day_{day}") is None:
                continue
            slots.append(
                (
                    day,
                    _clock(str(form.get(f"start_{day}") or "")),
                    _clock(str(form.get(f"end_{day}") or "")),
                )
            )
        destination = await complete_onboarding(
            session,
            tenant,
            business_name=business_name,
            rfc=rfc,
            address=address,
            categories=categories,
            min_guests=_number(min_guests),
            max_guests=_number(max_guests),
            whatsapp_phone=whatsapp_phone,
            contact_phone=contact_phone,
            show_prices_public=show_prices_public is not None,
            slots=slots,
            max_concurrent=_number(max_concurrent_events_per_slot),
            accepts_cash=accepts_cash is not None,
            accepts_transfer=accepts_transfer is not None,
            transfer_instructions=transfer_instructions,
            logo=logo,
        )
    except HTTPException as exc:
        detail = exc.detail if isinstance(exc.detail, str) else "Revisa el formulario"
        if _wants_json(request):
            return JSONResponse({"detail": detail}, status_code=exc.status_code)
        return await _wizard(
            request,
            session,
            tenant,
            error=detail,
            status_code=exc.status_code,
            posted=posted,
            categories=categories,
        )
    if _wants_json(request):
        return JSONResponse({"redirect": destination})
    return RedirectResponse(url=destination, status_code=302)


def _wants_json(request: Request) -> bool:
    return "application/json" in request.headers.get("accept", "")


async def _wizard(
    request: Request,
    session: SessionDep,
    tenant: Tenant,
    *,
    error: str,
    status_code: int,
    posted: dict[str, str] | None = None,
    categories: list[str] | None = None,
) -> Response:
    values = posted or {}
    has_posted = posted is not None
    chosen, slug_error = await preview_slug(
        session, tenant, values.get("business_name") or tenant.business_name
    )
    base = settings.IBISTRO_PUBLIC_BASE_URL.rstrip("/")
    return templates.TemplateResponse(
        request,
        "onboarding/wizard.html",
        {
            "error": error,
            "tenant": tenant,
            "categories": await load_categories(session),
            "selected_categories": categories or list(tenant.category_tags),
            "days": day_labels(),
            "values": values,
            "has_posted": has_posted,
            "public_url": f"{base}/c/{chosen}",
            "slug_error": slug_error or "",
            "prices_on": _box(
                values, "show_prices_public", tenant.show_prices_public, has_posted
            ),
            "cash_on": _box(values, "accepts_cash", tenant.accepts_cash, has_posted),
            "transfer_on": _box(
                values, "accepts_transfer", tenant.accepts_transfer, has_posted
            ),
        },
        status_code=status_code,
    )


def _box(values: dict[str, str], key: str, default: bool, has_posted: bool) -> bool:
    if has_posted:
        return key in values
    return default


def _posted(form: FormData) -> dict[str, str]:
    values: dict[str, str] = {}
    for key, value in form.multi_items():
        if isinstance(value, str):
            values[str(key)] = value
    return values


def _number(value: str) -> int:
    try:
        return int(value)
    except ValueError:
        raise HTTPException(status_code=422, detail="Indica un número válido")


def _clock(value: str) -> time:
    try:
        hour, minute = value.strip().split(":", 1)
        return time(int(hour), int(minute))
    except ValueError:
        raise HTTPException(status_code=422, detail="La hora no es válida")
