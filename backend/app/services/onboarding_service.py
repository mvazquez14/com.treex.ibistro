"""Provider onboarding: local uniqueness, Nuna trial, and the first warehouse."""

import re
from datetime import time
from pathlib import Path

from fastapi import HTTPException, Request, UploadFile, status
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.deps import get_current_tenant
from app.core.nuna_auth import organization_from_claims, read_session_claims
from app.models import ServiceScheduleSlot, Tenant, Warehouse
from app.schemas.catalog import CategoryRead
from app.services import nuna_client
from app.services.catalog_common import clean_phone
from app.services.impersonation import impersonated_name
from app.services.menu_catalog import list_service_categories
from app.services.menu_photos import save_tenant_logo, uploads_root
from app.services.slug import RESERVED_SLUGS, next_available_slug, slugify

_RFC = re.compile(r"[\s-]+")
_DAYS = (
    (0, "Lunes"),
    (1, "Martes"),
    (2, "Miércoles"),
    (3, "Jueves"),
    (4, "Viernes"),
    (5, "Sábado"),
    (6, "Domingo"),
)


def normalize_rfc(value: str) -> str:
    return _RFC.sub("", value).upper()


async def dashboard_destination(request: Request, session: AsyncSession) -> str | None:
    """Where an authenticated document request should go before the panel loads."""
    claims = read_session_claims(request)
    if not claims:
        return None
    org = organization_from_claims(claims)
    if org["is_superuser"] and impersonated_name(request) is None:
        return "/admin"
    try:
        tenant = await get_current_tenant(request, session)
    except HTTPException:
        return None
    path = request.url.path.removeprefix("/dashboard").strip("/")
    if not tenant.onboarding_completed:
        if path == "onboarding":
            return None
        return "/dashboard/onboarding"
    if path == "onboarding":
        return "/dashboard"
    return None


async def preview_slug(
    session: AsyncSession, tenant: Tenant, business_name: str
) -> tuple[str, str | None]:
    desired = slugify(business_name)
    if desired in RESERVED_SLUGS:
        return desired, "Ese nombre usa un enlace reservado. Elige otro."
    result = await session.exec(select(Tenant))
    taken = {row.slug for row in result.all() if row.id != tenant.id}
    return next_available_slug(business_name, taken), None


async def load_categories(session: AsyncSession) -> list[CategoryRead]:
    return await list_service_categories(session)


def day_labels() -> tuple[tuple[int, str], ...]:
    return _DAYS


async def complete_onboarding(
    session: AsyncSession,
    tenant: Tenant,
    *,
    business_name: str,
    rfc: str,
    address: str,
    categories: list[str],
    min_guests: int,
    max_guests: int,
    whatsapp_phone: str,
    contact_phone: str,
    show_prices_public: bool,
    slots: list[tuple[int, time, time]],
    max_concurrent: int,
    accepts_cash: bool,
    accepts_transfer: bool,
    transfer_instructions: str,
    logo: UploadFile | None,
) -> str:
    name = business_name.strip()
    if not name:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Indica el nombre del negocio",
        )
    cleaned_rfc = normalize_rfc(rfc)
    if len(cleaned_rfc) < 12 or len(cleaned_rfc) > 13:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="El RFC no es válido",
        )
    cleaned_address = address.strip()
    if not cleaned_address:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Indica la dirección",
        )
    if min_guests < 1 or max_guests < min_guests:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="El mínimo de invitados no puede ser mayor que el máximo",
        )
    whatsapp = clean_phone(whatsapp_phone)
    contact = clean_phone(contact_phone)
    if not whatsapp or not contact:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Indica el WhatsApp y el teléfono de contacto",
        )
    if not slots:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Elige al menos un día de servicio",
        )
    for day, start, end in slots:
        if day < 0 or day > 6 or end <= start:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="La hora de fin debe ser posterior a la de inicio",
            )
    if accepts_transfer and not transfer_instructions.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Indica la CLABE o las instrucciones de transferencia",
        )
    if not accepts_cash and not accepts_transfer:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Elige al menos una forma de pago",
        )
    slug, slug_error = await preview_slug(session, tenant, name)
    if slug_error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=slug_error,
        )
    conflict = await _identity_conflict(session, tenant.id, cleaned_rfc, whatsapp)
    if conflict:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=conflict)
    if logo is None or not logo.filename:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="La imagen debe ser PNG, JPG o WEBP.",
        )
    logo_url = await save_tenant_logo(tenant.id, logo)

    eligible = await nuna_client.check_trial_eligibility(
        tenant.nuna_org_id, cleaned_rfc, whatsapp
    )
    tenant.business_name = name
    tenant.slug = slug
    tenant.rfc = cleaned_rfc
    tenant.address = cleaned_address
    tenant.logo_url = logo_url
    tenant.category_tags = categories
    tenant.min_guests = min_guests
    tenant.max_guests = max_guests
    tenant.whatsapp_phone = whatsapp
    tenant.contact_phone = contact
    tenant.show_prices_public = show_prices_public
    tenant.max_concurrent_events_per_slot = max(1, max_concurrent)
    tenant.accepts_cash = accepts_cash
    tenant.accepts_transfer = accepts_transfer
    tenant.transfer_instructions = (
        transfer_instructions.strip() if accepts_transfer else ""
    )
    tenant.onboarding_completed = True
    if not eligible:
        tenant.has_active_plan = False
    session.add(tenant)
    await _replace_slots(session, tenant, slots)
    await _ensure_primary_warehouse(session, tenant)
    await session.commit()

    logo_path = _logo_file(logo_url)
    if eligible:
        await nuna_client.sync_organization_profile(
            nuna_org_id=tenant.nuna_org_id,
            business_name=name,
            rfc=cleaned_rfc,
            address=cleaned_address,
            whatsapp_phone=whatsapp,
            logo_path=logo_path,
        )
        return "/dashboard"
    await nuna_client.revoke_trial_eligibility(
        tenant.nuna_org_id, cleaned_rfc, whatsapp
    )
    return "/dashboard"


async def update_business_profile(
    session: AsyncSession,
    tenant: Tenant,
    *,
    address: str,
    whatsapp_phone: str,
    contact_phone: str,
    min_guests: int,
    max_guests: int,
    accepts_cash: bool,
    accepts_transfer: bool,
    transfer_instructions: str,
    show_prices_public: bool,
    service_duration_minutes: int = 120,
    travel_buffer_minutes: int = 60,
) -> Tenant:
    """Update the operational profile without reopening the trial."""
    cleaned_address = address.strip()
    if not cleaned_address:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Indica la dirección",
        )
    if min_guests < 1 or max_guests < min_guests:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="El mínimo de invitados no puede ser mayor que el máximo",
        )
    whatsapp = clean_phone(whatsapp_phone)
    contact = clean_phone(contact_phone)
    if not whatsapp or not contact:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Indica el WhatsApp y el teléfono de contacto",
        )
    if accepts_transfer and not transfer_instructions.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Indica la CLABE o las instrucciones de transferencia",
        )
    if not accepts_cash and not accepts_transfer:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Elige al menos una forma de pago",
        )
    conflict = await _identity_conflict(session, tenant.id, "", whatsapp)
    if conflict:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=conflict)
    tenant.address = cleaned_address
    tenant.whatsapp_phone = whatsapp
    tenant.contact_phone = contact
    tenant.min_guests = min_guests
    tenant.max_guests = max_guests
    tenant.accepts_cash = accepts_cash
    tenant.accepts_transfer = accepts_transfer
    tenant.transfer_instructions = (
        transfer_instructions.strip() if accepts_transfer else ""
    )
    tenant.show_prices_public = show_prices_public
    tenant.service_duration_minutes = service_duration_minutes
    tenant.travel_buffer_minutes = travel_buffer_minutes
    session.add(tenant)
    await session.commit()
    await session.refresh(tenant)
    return tenant


async def _identity_conflict(
    session: AsyncSession, tenant_id: object, rfc: str, phone: str
) -> str | None:
    result = await session.exec(select(Tenant))
    for row in result.all():
        if row.id == tenant_id:
            continue
        if rfc and normalize_rfc(row.rfc) == rfc:
            return "Ese RFC ya está registrado en otra cuenta"
        if phone and row.whatsapp_phone == phone:
            return "Ese WhatsApp ya está registrado en otra cuenta"
    return None


async def _replace_slots(
    session: AsyncSession,
    tenant: Tenant,
    slots: list[tuple[int, time, time]],
) -> None:
    existing = await session.exec(
        select(ServiceScheduleSlot).where(ServiceScheduleSlot.tenant_id == tenant.id)
    )
    for row in existing.all():
        await session.delete(row)
    for day, start, end in slots:
        session.add(
            ServiceScheduleSlot(
                tenant_id=tenant.id,
                day_of_week=day,
                start_time=start,
                end_time=end,
                is_active=True,
            )
        )


async def _ensure_primary_warehouse(session: AsyncSession, tenant: Tenant) -> None:
    existing = await session.exec(
        select(Warehouse).where(Warehouse.tenant_id == tenant.id)
    )
    if any(row.is_primary for row in existing.all()):
        return
    session.add(
        Warehouse(tenant_id=tenant.id, name="Almacén Principal", is_primary=True)
    )


def _logo_file(logo_url: str) -> Path | None:
    relative = logo_url.removeprefix("/uploads/")
    path = uploads_root() / relative
    return path if path.is_file() else None
