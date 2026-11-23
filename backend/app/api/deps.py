import hmac
from typing import Annotated, Any

from fastapi import Depends, Header, HTTPException, Request, status
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.core.db import get_session
from app.core.nuna_auth import organization_from_claims, read_session_claims
from app.models import Tenant
from app.services.impersonation import impersonation_target_id

SessionDep = Annotated[AsyncSession, Depends(get_session)]


def tenant_is_available(tenant: Tenant) -> bool:
    return bool(tenant.has_active_plan)


async def get_current_tenant(request: Request, session: SessionDep) -> Tenant:
    claims = read_session_claims(request)
    if not claims:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )
    org = organization_from_claims(claims)
    result = await session.exec(
        select(Tenant).where(Tenant.nuna_org_id == org["nuna_org_id"])
    )
    tenant = result.first()
    if org["is_superuser"]:
        target_id = impersonation_target_id(request, str(org["nuna_org_id"]))
        if target_id is not None:
            target = await session.get(Tenant, target_id)
            if target is not None:
                return target
    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )
    return tenant


CurrentTenant = Annotated[Tenant, Depends(get_current_tenant)]


async def require_active_plan(tenant: CurrentTenant) -> Tenant:
    if not tenant_is_available(tenant):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "message": "Suscripción inactiva — Ir a Nuna",
                "billing_url": settings.NUNA_BILLING_URL,
            },
        )
    return tenant


CurrentActiveTenant = Annotated[Tenant, Depends(require_active_plan)]


def require_orion_key(
    x_api_key: Annotated[str | None, Header()] = None,
) -> None:
    """Authenticate Orion with the shared service token."""
    expected = settings.ORION_SERVICE_TOKEN.strip()
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="La llave de Orion no está configurada",
        )
    provided = (x_api_key or "").strip()
    if not provided or not _keys_match(provided, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="La llave de Orion no es válida",
        )


def _keys_match(provided: str, expected: str) -> bool:
    left = provided.encode()
    right = expected.encode()
    if len(left) != len(right):
        return False
    return hmac.compare_digest(left, right)


OrionKey = Annotated[None, Depends(require_orion_key)]


async def require_superuser(request: Request) -> dict[str, Any]:
    claims = read_session_claims(request)
    if not claims:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )
    org = organization_from_claims(claims)
    if not org["is_superuser"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Se requiere un superusuario de Nuna",
        )
    return org


CurrentSuperuser = Annotated[dict[str, Any], Depends(require_superuser)]
