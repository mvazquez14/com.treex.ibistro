"""Nuna OAuth2 confidential-client flow. No PKCE."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import HTTPException, Request, status
from jwt.algorithms import RSAAlgorithm
from jwt.exceptions import InvalidTokenError, PyJWKClientError
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.core.security import decrypt_session
from app.models import Tenant
from app.services.tenants import allocate_unique_slug

logger = logging.getLogger(__name__)

MOCK_KEY_ID = "ibistro-mock"
_jwks_client: jwt.PyJWKClient | None = None
_mock_client: jwt.PyJWKClient | None = None
_mock_private_key: rsa.RSAPrivateKey | None = None


class StaticJWKClient(jwt.PyJWKClient):
    def __init__(self, jwks: dict[str, Any]) -> None:
        super().__init__("https://nuna.invalid/.well-known/jwks.json")
        self._jwks = jwks

    def fetch_data(self) -> Any:
        return self._jwks


def reset_jwks_client() -> None:
    global _jwks_client, _mock_client
    _jwks_client = None
    _mock_client = None


def _private_key() -> rsa.RSAPrivateKey:
    global _mock_private_key
    if _mock_private_key is None:
        _mock_private_key = rsa.generate_private_key(
            public_exponent=65537, key_size=2048
        )
    return _mock_private_key


def mock_jwks() -> dict[str, Any]:
    jwk = RSAAlgorithm.to_jwk(_private_key().public_key(), as_dict=True)
    if not isinstance(jwk, dict):
        raise RuntimeError("Unable to build the mock Nuna JWKS")
    jwk["kid"] = MOCK_KEY_ID
    jwk["use"] = "sig"
    jwk["alg"] = "RS256"
    return {"keys": [jwk]}


def sign_mock_token(claims: dict[str, Any]) -> str:
    private_pem = _private_key().private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    token = jwt.encode(
        claims,
        private_pem,
        algorithm="RS256",
        headers={"kid": MOCK_KEY_ID, "typ": "JWT"},
    )
    if isinstance(token, bytes):
        return token.decode()
    return token


def default_mock_claims() -> dict[str, Any]:
    now = datetime.now(UTC)
    return {
        "sub": "mock-org",
        "email": "demo@ibistro.mx",
        "iss": settings.NUNA_ISSUER,
        "aud": settings.NUNA_AUDIENCE,
        "exp": now + timedelta(hours=8),
        "iat": now,
        "is_superuser": False,
        "organization": {
            "id": "mock-org",
            "business_name": "Catering Demo",
            "rfc": "XAXX010101000",
            "address": "Guadalajara, Jalisco",
            "logo_url": None,
            "has_active_plan": True,
        },
        "subscription": {"plan": "ibistro", "status": "active", "valid_until": None},
    }


def jwks_client() -> jwt.PyJWKClient:
    global _jwks_client, _mock_client
    if settings.MOCK_MODE:
        if _mock_client is None:
            _mock_client = StaticJWKClient(mock_jwks())
        return _mock_client
    if _jwks_client is None:
        _jwks_client = jwt.PyJWKClient(settings.NUNA_JWKS_URL)
    return _jwks_client


def admin_mock_claims() -> dict[str, Any]:
    claims = default_mock_claims()
    claims["sub"] = "platform-admin"
    claims["email"] = "admin@ibistro.mx"
    claims["is_superuser"] = True
    claims["organization"] = {
        "id": "platform-admin",
        "business_name": "iBistro",
        "rfc": "",
        "address": "",
        "logo_url": None,
        "has_active_plan": True,
    }
    return claims


async def exchange_nuna_code(code: str, redirect_uri: str) -> str:
    if settings.MOCK_MODE:
        logger.debug("MOCK_MODE accepting Nuna authorization code=%s", code)
        claims = admin_mock_claims() if code == "admin" else default_mock_claims()
        return sign_mock_token(claims)
    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.post(
            settings.NUNA_TOKEN_URL,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect_uri,
                "client_id": settings.NUNA_CLIENT_ID,
                "client_secret": settings.NUNA_CLIENT_SECRET,
            },
        )
    if response.status_code >= 400:
        logger.error(
            "Nuna token exchange failed status=%s body=%s",
            response.status_code,
            (response.text or "")[:500],
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unable to exchange Nuna authorization code",
        )
    payload = response.json()
    token = payload.get("access_token")
    if not token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Nuna token response was empty",
        )
    return str(token)


def verify_nuna_jwt(
    token: str,
    *,
    client: jwt.PyJWKClient | None = None,
) -> dict[str, Any]:
    try:
        signing_key = (client or jwks_client()).get_signing_key_from_jwt(token)
        claims = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            audience=settings.NUNA_AUDIENCE,
            issuer=settings.NUNA_ISSUER,
        )
    except (InvalidTokenError, PyJWKClientError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Nuna SSO token",
        ) from exc
    if not isinstance(claims, dict):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Nuna SSO token",
        )
    return claims


def organization_from_claims(claims: dict[str, Any]) -> dict[str, Any]:
    raw_org = claims.get("organization")
    org = raw_org if isinstance(raw_org, dict) else {}
    nuna_org_id = str(
        org.get("id")
        or claims.get("org_id")
        or claims.get("nuna_org_id")
        or claims.get("sub")
        or ""
    ).strip()
    if not nuna_org_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Nuna token is missing an organization id",
        )
    business_name = str(
        org.get("business_name")
        or claims.get("business_name")
        or claims.get("email")
        or ""
    ).strip()
    if not business_name:
        business_name = "Proveedor"
    logo_url = org.get("logo_url", claims.get("logo_url"))
    if "has_active_plan" in org:
        has_active_plan = bool(org.get("has_active_plan"))
    elif "has_active_plan" in claims:
        has_active_plan = bool(claims.get("has_active_plan"))
    else:
        subscription = claims.get("subscription")
        subscription_status = ""
        if isinstance(subscription, dict):
            subscription_status = str(subscription.get("status") or "")
        has_active_plan = subscription_status == "active"
    return {
        "nuna_org_id": nuna_org_id,
        "business_name": business_name,
        "rfc": str(org.get("rfc") or claims.get("rfc") or ""),
        "address": str(org.get("address") or claims.get("address") or ""),
        "logo_url": str(logo_url) if logo_url else None,
        "has_active_plan": has_active_plan,
        "is_superuser": bool(claims.get("is_superuser")),
        "email": str(claims.get("email") or ""),
    }


async def upsert_tenant_from_claims(
    *,
    session: AsyncSession,
    claims: dict[str, Any],
) -> Tenant:
    data = organization_from_claims(claims)
    result = await session.exec(
        select(Tenant).where(Tenant.nuna_org_id == data["nuna_org_id"])
    )
    tenant = result.first()
    if tenant:
        tenant.business_name = str(data["business_name"])
        tenant.rfc = str(data["rfc"])
        tenant.address = str(data["address"])
        tenant.logo_url = (
            data["logo_url"] if isinstance(data["logo_url"], str) else None
        )
        tenant.has_active_plan = bool(data["has_active_plan"])
        session.add(tenant)
        await session.commit()
        await session.refresh(tenant)
        return tenant

    slug = await allocate_unique_slug(session, str(data["business_name"]))
    tenant = Tenant(
        nuna_org_id=str(data["nuna_org_id"]),
        slug=slug,
        business_name=str(data["business_name"]),
        rfc=str(data["rfc"]),
        address=str(data["address"]),
        logo_url=data["logo_url"] if isinstance(data["logo_url"], str) else None,
        has_active_plan=bool(data["has_active_plan"]),
    )
    session.add(tenant)
    await session.commit()
    await session.refresh(tenant)
    return tenant


def nuna_login_redirect(return_to: str = "/dashboard/menu") -> str:
    from urllib.parse import urlencode

    query = urlencode(
        {
            "redirect_uri": settings.NUNA_REDIRECT_URI,
            "return_to": return_to or "/dashboard/menu",
            "app": settings.NUNA_CLIENT_ID,
        }
    )
    return f"{settings.NUNA_LOGIN_URL}?{query}"


def read_session_claims(request: Request) -> dict[str, Any] | None:
    raw = request.cookies.get(settings.SESSION_COOKIE_NAME)
    if not raw:
        return None
    try:
        return verify_nuna_jwt(decrypt_session(raw))
    except Exception:
        logger.debug("Ignoring unreadable Nuna session cookie", exc_info=True)
        return None
