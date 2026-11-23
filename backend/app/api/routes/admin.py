"""Super-admin desk for categories, providers, and catalog cloning."""

from uuid import UUID

from fastapi import APIRouter, Form, HTTPException, Request
from starlette.responses import RedirectResponse, Response

from app.api.deps import CurrentSuperuser, SessionDep
from app.api.forms import checked, int_field
from app.core.config import settings
from app.services import admin_panel
from app.services.impersonation import sign_impersonation
from app.templating import failure, render

router = APIRouter(prefix="/admin", tags=["admin"])


def _cookie_secure() -> bool:
    return not settings.FRONTEND_HOST.startswith("http://localhost")


async def _render(
    request: Request,
    session: SessionDep,
    error: str | None = None,
    status_code: int = 200,
) -> Response:
    screen = await admin_panel.admin_screen(session)
    return render(
        request,
        "admin/index.html",
        "admin/panel.html",
        {"section": "admin", "screen": screen, "error": error},
        status_code,
    )


@router.get("")
async def admin_page(
    request: Request, session: SessionDep, _actor: CurrentSuperuser
) -> Response:
    return await _render(request, session)


@router.post("/categories")
async def create_category(
    request: Request,
    session: SessionDep,
    actor: CurrentSuperuser,
    name: str = Form(),
    icon: str = Form(default=""),
    is_active: str = Form(default=""),
) -> Response:
    try:
        row = await admin_panel.save_category(
            session,
            category_id=None,
            name=name,
            icon=icon,
            is_active=checked(is_active),
        )
        await admin_panel.write_audit(
            session,
            actor_nuna_org_id=str(actor["nuna_org_id"]),
            actor_email=str(actor["email"]),
            action="upsert_category",
            target_tenant_id=None,
            detail={"category_id": str(row.id), "name": row.name},
        )
        await session.commit()
    except HTTPException as exc:
        await session.rollback()
        message, code = failure(exc)
        return await _render(request, session, message, code)
    return await _render(request, session)


@router.post("/categories/{category_id}")
async def update_category(
    request: Request,
    session: SessionDep,
    actor: CurrentSuperuser,
    category_id: UUID,
    name: str = Form(),
    icon: str = Form(default=""),
    is_active: str = Form(default=""),
) -> Response:
    try:
        row = await admin_panel.save_category(
            session,
            category_id=category_id,
            name=name,
            icon=icon,
            is_active=checked(is_active),
        )
        await admin_panel.write_audit(
            session,
            actor_nuna_org_id=str(actor["nuna_org_id"]),
            actor_email=str(actor["email"]),
            action="upsert_category",
            target_tenant_id=None,
            detail={"category_id": str(row.id), "name": row.name},
        )
        await session.commit()
    except HTTPException as exc:
        await session.rollback()
        message, code = failure(exc)
        return await _render(request, session, message, code)
    return await _render(request, session)


@router.post("/tenants/{tenant_id}")
async def update_tenant(
    request: Request,
    session: SessionDep,
    actor: CurrentSuperuser,
    tenant_id: UUID,
) -> Response:
    form = await request.form()
    modules = [value for value in form.getlist("module") if isinstance(value, str)]
    score = form.get("concierge_priority_score")
    verified = form.get("is_verified_concierge")
    try:
        tenant = await admin_panel.update_tenant(
            session,
            tenant_id,
            is_verified_concierge=checked(
                verified if isinstance(verified, str) else None
            ),
            concierge_priority_score=int_field(
                score if isinstance(score, str) else "", "La prioridad"
            ),
            enabled_modules=modules,
        )
        await admin_panel.write_audit(
            session,
            actor_nuna_org_id=str(actor["nuna_org_id"]),
            actor_email=str(actor["email"]),
            action="update_tenant",
            target_tenant_id=tenant.id,
            detail={"verified": str(tenant.is_verified_concierge)},
        )
        await session.commit()
    except HTTPException as exc:
        await session.rollback()
        message, code = failure(exc)
        return await _render(request, session, message, code)
    return await _render(request, session)


@router.post("/tenants/{tenant_id}/clone-templates")
async def clone_templates(
    request: Request,
    session: SessionDep,
    actor: CurrentSuperuser,
    tenant_id: UUID,
) -> Response:
    try:
        result = await admin_panel.clone_for_tenant(session, tenant_id)
        await admin_panel.write_audit(
            session,
            actor_nuna_org_id=str(actor["nuna_org_id"]),
            actor_email=str(actor["email"]),
            action="clone_templates",
            target_tenant_id=tenant_id,
            detail={
                "ingredients": str(result.ingredients),
                "recipes": str(result.recipes),
            },
        )
        await session.commit()
    except HTTPException as exc:
        await session.rollback()
        message, code = failure(exc)
        return await _render(request, session, message, code)
    return await _render(request, session)


@router.post("/impersonate/stop")
async def stop_impersonation(session: SessionDep, actor: CurrentSuperuser) -> Response:
    await admin_panel.write_audit(
        session,
        actor_nuna_org_id=str(actor["nuna_org_id"]),
        actor_email=str(actor["email"]),
        action="stop_impersonation",
        target_tenant_id=None,
        detail={},
    )
    await session.commit()
    response = RedirectResponse(url="/admin", status_code=302)
    response.delete_cookie(key=settings.IMPERSONATION_COOKIE_NAME, path="/")
    return response


@router.post("/impersonate/{tenant_id}")
async def impersonate(
    session: SessionDep,
    actor: CurrentSuperuser,
    tenant_id: UUID,
) -> Response:
    tenant = await admin_panel.require_provider(session, tenant_id)
    await admin_panel.write_audit(
        session,
        actor_nuna_org_id=str(actor["nuna_org_id"]),
        actor_email=str(actor["email"]),
        action="impersonate",
        target_tenant_id=tenant.id,
        detail={"slug": tenant.slug},
    )
    await session.commit()
    response = RedirectResponse(url="/dashboard/menu", status_code=302)
    response.set_cookie(
        key=settings.IMPERSONATION_COOKIE_NAME,
        value=sign_impersonation(
            str(actor["nuna_org_id"]), tenant.id, tenant.business_name
        ),
        httponly=True,
        samesite="lax",
        secure=_cookie_secure(),
        path="/",
        max_age=8 * 60 * 60,
    )
    return response
