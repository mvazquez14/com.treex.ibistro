"""Schedule, gallery, and delivery zones."""

from uuid import UUID

from fastapi import APIRouter, status

from app.api.deps import CurrentActiveTenant, SessionDep
from app.schemas.quotes import (
    PhotoIn,
    PhotoRead,
    SlotIn,
    SlotRead,
    ZoneIn,
    ZoneRead,
)
from app.services import schedule_catalog as catalog

router = APIRouter(prefix="/schedule", tags=["schedule"])


@router.get("/slots", response_model=list[SlotRead])
async def list_slots(
    session: SessionDep, tenant: CurrentActiveTenant
) -> list[SlotRead]:
    return await catalog.list_slot_reads(session, tenant.id)


@router.post("/slots", response_model=SlotRead, status_code=status.HTTP_201_CREATED)
async def create_slot(
    session: SessionDep, tenant: CurrentActiveTenant, data: SlotIn
) -> SlotRead:
    created = await catalog.create_slot(session, tenant.id, data)
    await session.commit()
    return created


@router.delete("/slots/{slot_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_slot(
    session: SessionDep, tenant: CurrentActiveTenant, slot_id: UUID
) -> None:
    await catalog.delete_slot(session, tenant.id, slot_id)
    await session.commit()


@router.get("/photos", response_model=list[PhotoRead])
async def list_photos(
    session: SessionDep, tenant: CurrentActiveTenant
) -> list[PhotoRead]:
    return await catalog.list_photos(session, tenant.id)


@router.post("/photos", response_model=PhotoRead, status_code=status.HTTP_201_CREATED)
async def create_photo(
    session: SessionDep, tenant: CurrentActiveTenant, data: PhotoIn
) -> PhotoRead:
    created = await catalog.create_photo(session, tenant.id, data)
    await session.commit()
    return created


@router.delete("/photos/{photo_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_photo(
    session: SessionDep, tenant: CurrentActiveTenant, photo_id: UUID
) -> None:
    await catalog.delete_photo(session, tenant.id, photo_id)
    await session.commit()


@router.get("/zones", response_model=list[ZoneRead])
async def list_zones(
    session: SessionDep, tenant: CurrentActiveTenant
) -> list[ZoneRead]:
    return await catalog.list_zones(session, tenant.id)


@router.post("/zones", response_model=ZoneRead, status_code=status.HTTP_201_CREATED)
async def create_zone(
    session: SessionDep, tenant: CurrentActiveTenant, data: ZoneIn
) -> ZoneRead:
    created = await catalog.create_zone(session, tenant.id, data)
    await session.commit()
    return created
