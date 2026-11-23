from fastapi import APIRouter

from app.api.deps import CurrentTenant
from app.core.config import settings

router = APIRouter(prefix="/subscription", tags=["subscription"])


@router.get("/status")
async def subscription_status(tenant: CurrentTenant) -> dict[str, str | bool | None]:
    message = None if tenant.has_active_plan else "Suscripción inactiva — Ir a Nuna"
    return {
        "has_active_plan": tenant.has_active_plan,
        "billing_url": settings.NUNA_BILLING_URL,
        "message": message,
    }
