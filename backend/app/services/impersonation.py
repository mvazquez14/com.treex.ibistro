"""Signed cookie that lets a Nuna superuser act as a provider."""

import json
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from starlette.requests import Request

from app.core.config import settings
from app.core.nuna_auth import organization_from_claims, read_session_claims
from app.core.security import decrypt_session, encrypt_session

_HOURS = 8


def sign_impersonation(
    actor_nuna_org_id: str, tenant_id: UUID, business_name: str
) -> str:
    payload = {
        "actor": actor_nuna_org_id,
        "tenant_id": str(tenant_id),
        "business_name": business_name,
        "exp": (datetime.now(UTC) + timedelta(hours=_HOURS)).isoformat(),
    }
    return encrypt_session(json.dumps(payload))


def impersonation_target_id(request: Request, actor_nuna_org_id: str) -> UUID | None:
    payload = _payload(request)
    if payload is None or payload.get("actor") != actor_nuna_org_id:
        return None
    raw = payload.get("tenant_id")
    try:
        return UUID(str(raw))
    except ValueError:
        return None


def impersonated_name(request: Request) -> str | None:
    claims = read_session_claims(request)
    if not claims:
        return None
    org = organization_from_claims(claims)
    if not org["is_superuser"]:
        return None
    payload = _payload(request)
    if payload is None or payload.get("actor") != org["nuna_org_id"]:
        return None
    name = payload.get("business_name")
    if isinstance(name, str) and name.strip():
        return name.strip()
    return "el proveedor"


def _payload(request: Request) -> dict[str, Any] | None:
    raw = request.cookies.get(settings.IMPERSONATION_COOKIE_NAME)
    if not raw:
        return None
    try:
        loaded = json.loads(decrypt_session(raw))
    except Exception:  # untrusted cookie: InvalidToken is not a ValueError
        return None
    if not isinstance(loaded, dict):
        return None
    try:
        exp = datetime.fromisoformat(str(loaded.get("exp")))
    except ValueError:
        return None
    if exp.tzinfo is None:
        exp = exp.replace(tzinfo=UTC)
    if exp < datetime.now(UTC):
        return None
    return loaded
