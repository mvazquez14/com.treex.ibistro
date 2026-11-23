from fastapi import APIRouter, Depends

from app.api.deps import CurrentActiveTenant, require_active_plan

router = APIRouter(
    prefix="/operations",
    tags=["operations"],
    dependencies=[Depends(require_active_plan)],
)


@router.get("/ping")
async def operations_ping(tenant: CurrentActiveTenant) -> dict[str, str]:
    return {"tenant_id": str(tenant.id), "slug": tenant.slug}
