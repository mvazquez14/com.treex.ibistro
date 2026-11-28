from urllib.parse import urlencode

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import JSONResponse, RedirectResponse

from app.api.deps import SessionDep, get_current_tenant
from app.core.config import settings
from app.core.nuna_auth import (
    exchange_nuna_code,
    nuna_login_redirect,
    organization_from_claims,
    read_session_claims,
    upsert_tenant_from_claims,
    verify_nuna_jwt,
)
from app.core.security import encrypt_session
from app.services.impersonation import impersonated_name

router = APIRouter(tags=["auth"])


DEFAULT_RETURN_TO = "/dashboard"


def _safe_return_to(value: str | None) -> str:
    if not value or not value.startswith("/") or value.startswith("//"):
        return DEFAULT_RETURN_TO
    if "\\" in value or "://" in value:
        return DEFAULT_RETURN_TO
    return value


def set_session_cookie(response: Response, nuna_jwt: str) -> None:
    response.set_cookie(
        key=settings.SESSION_COOKIE_NAME,
        value=encrypt_session(nuna_jwt),
        httponly=True,
        samesite="lax",
        secure=not settings.FRONTEND_HOST.startswith("http://localhost"),
        path="/",
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(key=settings.SESSION_COOKIE_NAME, path="/")


@router.get("/login")
async def login_entry() -> RedirectResponse:
    return RedirectResponse(
        url=nuna_login_redirect(DEFAULT_RETURN_TO),
        status_code=302,
    )


@router.get("/api/auth/callback")
async def nuna_callback(
    session: SessionDep,
    code: str | None = None,
    return_to: str | None = None,
) -> RedirectResponse:
    if not code:
        return RedirectResponse(
            url=nuna_login_redirect(DEFAULT_RETURN_TO),
            status_code=302,
        )
    nuna_jwt = await exchange_nuna_code(code, settings.NUNA_REDIRECT_URI)
    claims = verify_nuna_jwt(nuna_jwt)
    await upsert_tenant_from_claims(session=session, claims=claims)
    response = RedirectResponse(url=_safe_return_to(return_to), status_code=302)
    set_session_cookie(response, nuna_jwt)
    return response


@router.get("/api/auth/session")
async def nuna_session(request: Request, session: SessionDep) -> JSONResponse:
    claims = read_session_claims(request)
    if not claims:
        return JSONResponse(
            status_code=401,
            content={
                "authenticated": False,
                "login_url": nuna_login_redirect(DEFAULT_RETURN_TO),
            },
        )
    org = organization_from_claims(claims)
    try:
        tenant = await get_current_tenant(request, session)
    except HTTPException:
        tenant = None
    logout_query = urlencode(
        {"post_logout_redirect_uri": settings.NUNA_POST_LOGOUT_REDIRECT_URI}
    )
    return JSONResponse(
        {
            "authenticated": True,
            "nuna_org_id": org["nuna_org_id"],
            "email": org["email"],
            "business_name": tenant.business_name if tenant else org["business_name"],
            "slug": tenant.slug if tenant else None,
            "has_active_plan": tenant.has_active_plan
            if tenant
            else org["has_active_plan"],
            "is_superuser": org["is_superuser"],
            "billing_url": settings.NUNA_BILLING_URL,
            "logout_url": f"{settings.NUNA_LOGOUT_URL}?{logout_query}",
            "public_base_url": settings.IBISTRO_PUBLIC_BASE_URL.rstrip("/"),
            "impersonating": impersonated_name(request),
            "onboarding_completed": tenant.onboarding_completed if tenant else False,
        }
    )


@router.get("/api/auth/logout")
async def nuna_logout() -> RedirectResponse:
    query = urlencode(
        {"post_logout_redirect_uri": settings.NUNA_POST_LOGOUT_REDIRECT_URI}
    )
    response = RedirectResponse(
        url=f"{settings.NUNA_LOGOUT_URL}?{query}",
        status_code=302,
    )
    clear_session_cookie(response)
    return response
