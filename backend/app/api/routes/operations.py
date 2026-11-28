from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.api.deps import CurrentActiveTenant, SessionDep, require_active_plan
from app.models import Tenant
from app.services.onboarding_service import update_business_profile

router = APIRouter(
    prefix="/operations",
    tags=["operations"],
    dependencies=[Depends(require_active_plan)],
)


class BusinessProfile(BaseModel):
    business_name: str
    rfc: str
    slug: str
    logo_url: str | None
    address: str
    whatsapp_phone: str
    contact_phone: str
    min_guests: int
    max_guests: int
    accepts_cash: bool
    accepts_transfer: bool
    transfer_instructions: str
    show_prices_public: bool
    service_duration_minutes: int
    travel_buffer_minutes: int


class BusinessProfileUpdate(BaseModel):
    address: str
    whatsapp_phone: str
    contact_phone: str
    min_guests: int = Field(ge=1)
    max_guests: int = Field(ge=1)
    accepts_cash: bool
    accepts_transfer: bool
    transfer_instructions: str = ""
    show_prices_public: bool = True
    service_duration_minutes: int = Field(default=120, ge=30, le=720)
    travel_buffer_minutes: int = Field(default=60, ge=0, le=360)


def _profile(tenant: Tenant) -> BusinessProfile:
    return BusinessProfile(
        business_name=tenant.business_name,
        rfc=tenant.rfc,
        slug=tenant.slug,
        logo_url=tenant.logo_url,
        address=tenant.address,
        whatsapp_phone=tenant.whatsapp_phone,
        contact_phone=tenant.contact_phone,
        min_guests=tenant.min_guests,
        max_guests=tenant.max_guests,
        accepts_cash=tenant.accepts_cash,
        accepts_transfer=tenant.accepts_transfer,
        transfer_instructions=tenant.transfer_instructions,
        show_prices_public=tenant.show_prices_public,
        service_duration_minutes=tenant.service_duration_minutes,
        travel_buffer_minutes=tenant.travel_buffer_minutes,
    )


@router.get("/ping")
async def operations_ping(tenant: CurrentActiveTenant) -> dict[str, str]:
    return {"tenant_id": str(tenant.id), "slug": tenant.slug}


@router.get("/profile", response_model=BusinessProfile)
async def read_profile(tenant: CurrentActiveTenant) -> BusinessProfile:
    return _profile(tenant)


@router.patch("/profile", response_model=BusinessProfile)
async def patch_profile(
    body: BusinessProfileUpdate,
    tenant: CurrentActiveTenant,
    session: SessionDep,
) -> BusinessProfile:
    saved = await update_business_profile(
        session,
        tenant,
        address=body.address,
        whatsapp_phone=body.whatsapp_phone,
        contact_phone=body.contact_phone,
        min_guests=body.min_guests,
        max_guests=body.max_guests,
        accepts_cash=body.accepts_cash,
        accepts_transfer=body.accepts_transfer,
        transfer_instructions=body.transfer_instructions,
        show_prices_public=body.show_prices_public,
        service_duration_minutes=body.service_duration_minutes,
        travel_buffer_minutes=body.travel_buffer_minutes,
    )
    return _profile(saved)
