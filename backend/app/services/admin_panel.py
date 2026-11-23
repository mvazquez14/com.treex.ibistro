"""Super-admin catalog, provider flags, and the audit log."""

from uuid import UUID

from fastapi import HTTPException, status
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.platform import PlatformAuditLog
from app.models.tenant import ServiceCategory, Tenant
from app.services.catalog_clone import CloneResult, clone_master_catalog
from app.services.catalog_common import clean_name
from app.services.concierge import MASTER_CATALOG_ORG_ID
from app.services.slug import slugify

KNOWN_MODULES = ("catering_core", "concierge_bot", "pos_lite")
MODULE_LABELS = {
    "catering_core": "Núcleo de catering",
    "concierge_bot": "Concierge",
    "pos_lite": "Punto de venta",
}


class AdminCategory:
    def __init__(self, row: ServiceCategory) -> None:
        self.id = row.id
        self.name = row.name
        self.slug = row.slug
        self.icon = row.icon
        self.is_active = row.is_active


class AdminTenant:
    def __init__(self, row: Tenant) -> None:
        self.id = row.id
        self.business_name = row.business_name
        self.slug = row.slug
        self.has_active_plan = row.has_active_plan
        self.is_verified_concierge = row.is_verified_concierge
        self.concierge_priority_score = row.concierge_priority_score
        self.enabled_modules = list(row.enabled_modules)


class AdminScreen:
    def __init__(
        self, categories: list[AdminCategory], tenants: list[AdminTenant]
    ) -> None:
        self.categories = categories
        self.tenants = tenants
        self.modules = KNOWN_MODULES
        self.module_labels = MODULE_LABELS


async def admin_screen(session: AsyncSession) -> AdminScreen:
    categories = await _categories(session)
    tenants = [
        AdminTenant(row)
        for row in await _tenants(session)
        if row.nuna_org_id != MASTER_CATALOG_ORG_ID
    ]
    tenants.sort(key=lambda row: row.business_name.lower())
    return AdminScreen(
        [AdminCategory(row) for row in categories],
        tenants,
    )


async def save_category(
    session: AsyncSession,
    *,
    category_id: UUID | None,
    name: str,
    icon: str,
    is_active: bool,
) -> ServiceCategory:
    cleaned = clean_name(name, limit=80)
    slug = slugify(cleaned)
    rows = await _categories(session)
    if any(row.slug == slug and row.id != category_id for row in rows):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Esa categoría ya existe",
        )
    if category_id is None:
        row = ServiceCategory(
            name=cleaned, slug=slug, icon=icon.strip()[:80], is_active=is_active
        )
        session.add(row)
        await session.flush()
        return row
    found = next((item for item in rows if item.id == category_id), None)
    if found is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No se encontró la categoría",
        )
    found.name = cleaned
    found.slug = slug
    found.icon = icon.strip()[:80]
    found.is_active = is_active
    session.add(found)
    await session.flush()
    return found


async def update_tenant(
    session: AsyncSession,
    tenant_id: UUID,
    *,
    is_verified_concierge: bool,
    concierge_priority_score: int,
    enabled_modules: list[str],
) -> Tenant:
    if concierge_priority_score < 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="La prioridad no puede ser negativa",
        )
    tenant = await require_provider(session, tenant_id)
    unknown = [name for name in enabled_modules if name not in KNOWN_MODULES]
    if unknown:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="El módulo no es válido",
        )
    tenant.is_verified_concierge = is_verified_concierge
    tenant.concierge_priority_score = concierge_priority_score
    tenant.enabled_modules = [name for name in KNOWN_MODULES if name in enabled_modules]
    session.add(tenant)
    await session.flush()
    return tenant


async def clone_for_tenant(session: AsyncSession, tenant_id: UUID) -> CloneResult:
    await require_provider(session, tenant_id)
    return await clone_master_catalog(session, tenant_id)


async def write_audit(
    session: AsyncSession,
    *,
    actor_nuna_org_id: str,
    actor_email: str,
    action: str,
    target_tenant_id: UUID | None,
    detail: dict[str, str],
) -> PlatformAuditLog:
    row = PlatformAuditLog(
        actor_nuna_org_id=actor_nuna_org_id,
        actor_email=actor_email,
        action=action,
        target_tenant_id=target_tenant_id,
        detail=detail,
    )
    session.add(row)
    await session.flush()
    return row


async def require_provider(session: AsyncSession, tenant_id: UUID) -> Tenant:
    tenant = await session.get(Tenant, tenant_id)
    if tenant is None or tenant.nuna_org_id == MASTER_CATALOG_ORG_ID:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No se encontró el proveedor",
        )
    return tenant


async def _categories(session: AsyncSession) -> list[ServiceCategory]:
    result = await session.exec(select(ServiceCategory))
    rows = list(result.all())
    rows.sort(key=lambda row: row.name.lower())
    return rows


async def _tenants(session: AsyncSession) -> list[Tenant]:
    result = await session.exec(select(Tenant))
    return list(result.all())
