from hmac import compare_digest
from typing import Any, Literal

from fastapi import APIRouter, Header, HTTPException, status
from pydantic import BaseModel
from sqlmodel import select

from app.api.deps import SessionDep
from app.core.config import settings
from app.core.redis import claim_webhook_event
from app.models import Tenant

router = APIRouter(tags=["webhooks"])


class NunaWebhookPayload(BaseModel):
    nuna_org_id: str
    has_active_plan: bool
    event: Literal[
        "trial.started",
        "payment.succeeded",
        "payment.failed",
        "subscription.suspended",
    ]
    event_id: str | None = None


def _require_webhook_secret(authorization: str | None) -> None:
    expected = settings.NUNA_WEBHOOK_SECRET
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Nuna webhook is not configured",
        )
    provided = ""
    if authorization and authorization.lower().startswith("bearer "):
        provided = authorization.split(" ", 1)[1].strip()
    if not provided or not compare_digest(provided, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid webhook secret",
        )


@router.post("/webhooks/nuna")
async def nuna_webhook(
    payload: NunaWebhookPayload,
    session: SessionDep,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    _require_webhook_secret(authorization)
    result = await session.exec(
        select(Tenant).where(Tenant.nuna_org_id == payload.nuna_org_id)
    )
    tenant = result.first()
    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found"
        )
    if payload.event_id and not await claim_webhook_event(payload.event_id):
        return {"status": "duplicate"}
    tenant.has_active_plan = payload.has_active_plan
    session.add(tenant)
    await session.commit()
    return {"status": "ok", "has_active_plan": tenant.has_active_plan}
