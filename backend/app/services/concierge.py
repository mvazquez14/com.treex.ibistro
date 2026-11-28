"""Search and quoting for the Orion WhatsApp concierge."""

from datetime import date, time
from urllib.parse import urlencode
from uuid import UUID

from fastapi import HTTPException, status
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.models.enums import LeadSource
from app.models.tenant import ServiceCategory, Tenant
from app.schemas.concierge import (
    ConciergeAvailability,
    ConciergeCategory,
    ConciergeDay,
    ConciergeMenu,
    ConciergeProvider,
    ConciergeQuoteIn,
)
from app.schemas.quotes import PublicQuoteIn, PublicQuoteOut, PublicSlot
from app.services.availability import open_slots, upcoming_days
from app.services.quoting import landing_page, public_profile, submit_quote_for_tenant

MASTER_CATALOG_ORG_ID = "master-catalog"
_ALLOWED_SOURCES = {LeadSource.WHATSAPP_DIRECT, LeadSource.WHATSAPP_CONCIERGE}


async def list_categories(session: AsyncSession) -> list[ConciergeCategory]:
    result = await session.exec(select(ServiceCategory))
    rows = [row for row in result.all() if row.is_active]
    rows.sort(key=lambda row: row.name.lower())
    return [
        ConciergeCategory(id=row.id, name=row.name, slug=row.slug, icon=row.icon)
        for row in rows
    ]


async def search_providers(
    session: AsyncSession,
    *,
    category_slug: str,
    guest_count: int,
    event_date: date,
) -> list[ConciergeProvider]:
    if guest_count < 1:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Indica al menos un invitado",
        )
    category = await _category(session, category_slug)
    found: list[ConciergeProvider] = []
    for tenant in await _tenants(session):
        if not _searchable(tenant, category, guest_count):
            continue
        slots = await _public_slots(session, tenant, event_date)
        if not slots:
            continue
        found.append(
            ConciergeProvider(
                id=tenant.id,
                slug=tenant.slug,
                business_name=tenant.business_name,
                concierge_priority_score=tenant.concierge_priority_score,
                landing_url=_landing_url(
                    tenant, event_date, guest_count, category.slug
                ),
                slots=slots,
            )
        )
    found.sort(
        key=lambda row: (-row.concierge_priority_score, row.business_name.lower())
    )
    return found[:3]


async def provider_availability(
    session: AsyncSession, provider_id: UUID
) -> ConciergeAvailability:
    tenant = await _provider(session, provider_id)
    days: list[ConciergeDay] = []
    for event_date in upcoming_days(date.today()):
        slots = await _public_slots(session, tenant, event_date)
        if slots:
            days.append(ConciergeDay(event_date=event_date, slots=slots))
    return ConciergeAvailability(
        provider_id=tenant.id,
        business_name=tenant.business_name,
        days=days,
    )


async def provider_menu(session: AsyncSession, provider_id: UUID) -> ConciergeMenu:
    tenant = await _provider(session, provider_id)
    page = await landing_page(session, tenant.slug)
    profile = public_profile(page)
    return ConciergeMenu(
        provider_id=tenant.id,
        business_name=tenant.business_name,
        show_prices=profile.show_prices,
        packages=profile.packages,
        extras=profile.extras,
    )


async def create_quote(session: AsyncSession, data: ConciergeQuoteIn) -> PublicQuoteOut:
    if data.source not in _ALLOWED_SOURCES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="El origen de la cotización no es válido",
        )
    tenant = await _provider(session, data.provider_id)
    return await submit_quote_for_tenant(
        session,
        tenant,
        PublicQuoteIn(
            package_id=data.package_id,
            event_date=data.event_date,
            slot_id=data.slot_id,
            start_time=data.start_time,
            guest_count=data.guest_count,
            full_name=data.full_name,
            phone=data.phone,
            whatsapp_phone=data.whatsapp_phone,
            email=data.email,
            venue_address=data.venue_address,
            special_requests=data.special_requests,
            selected_options=data.selected_options,
            extras=data.extras,
            delivery_zone_id=data.delivery_zone_id,
        ),
        data.source,
    )


def _searchable(tenant: Tenant, category: ServiceCategory, guest_count: int) -> bool:
    if tenant.nuna_org_id == MASTER_CATALOG_ORG_ID:
        return False
    if not tenant.has_active_plan or not tenant.is_verified_concierge:
        return False
    if guest_count < tenant.min_guests or guest_count > tenant.max_guests:
        return False
    tags = {tag.strip().lower() for tag in tenant.category_tags if tag.strip()}
    return category.slug.lower() in tags or category.name.lower() in tags


async def _public_slots(
    session: AsyncSession, tenant: Tenant, event_date: date
) -> list[PublicSlot]:
    rows = await open_slots(session, tenant, event_date)
    slots: list[PublicSlot] = []
    for slot, start, remaining in rows:
        end_at = start.hour * 60 + start.minute + tenant.service_duration_minutes
        end = time(hour=(end_at // 60) % 24, minute=end_at % 60)
        slots.append(
            PublicSlot(
                id=slot.id,
                label=f"{start:%H:%M}",
                start_time=f"{start:%H:%M}",
                end_time=f"{end:%H:%M}",
                remaining=remaining,
            )
        )
    return slots


def _landing_url(
    tenant: Tenant, event_date: date, guest_count: int, category_slug: str
) -> str:
    base = settings.IBISTRO_PUBLIC_BASE_URL.rstrip("/")
    query = urlencode(
        {
            "event_date": event_date.isoformat(),
            "guest_count": str(guest_count),
            "category": category_slug,
        }
    )
    return f"{base}/c/{tenant.slug}?{query}"


async def _category(session: AsyncSession, slug: str) -> ServiceCategory:
    result = await session.exec(select(ServiceCategory))
    wanted = slug.strip().lower()
    for row in result.all():
        if row.slug.lower() == wanted and row.is_active:
            return row
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="No se encontró la categoría",
    )


async def _provider(session: AsyncSession, provider_id: UUID) -> Tenant:
    tenant = await session.get(Tenant, provider_id)
    if tenant is None or tenant.nuna_org_id == MASTER_CATALOG_ORG_ID:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No se encontró el proveedor",
        )
    return tenant


async def _tenants(session: AsyncSession) -> list[Tenant]:
    result = await session.exec(select(Tenant))
    return list(result.all())
