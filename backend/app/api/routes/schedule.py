"""Schedule, gallery, and delivery zones."""

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Query, status

from app.api.deps import CurrentActiveTenant, SessionDep
from app.schemas.quotes import (
    PhotoIn,
    PhotoRead,
    ScheduleChoice,
    SlotIn,
    SlotRead,
    ZoneIn,
    ZoneRead,
)
from app.services import schedule_catalog as catalog
from app.services.availability import clock_text, open_slots

router = APIRouter(prefix="/schedule", tags=["schedule"])


@router.get("/openings", response_model=list[ScheduleChoice])
async def list_openings(
    session: SessionDep,
    tenant: CurrentActiveTenant,
    day: date = Query(alias="date"),
    ignore_reservation_id: UUID | None = None,
) -> list[ScheduleChoice]:
    rows = await open_slots(session, tenant, day, ignore_reservation_id)
    return [
        ScheduleChoice(
            event_date=day,
            slot_id=slot.id,
            start_time=clock_text(start),
        )
        for slot, start, _remaining in rows
    ]


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


@router.patch("/slots/{slot_id}", response_model=SlotRead)
async def patch_slot(
    session: SessionDep, tenant: CurrentActiveTenant, slot_id: UUID, data: SlotIn
) -> SlotRead:
    updated = await catalog.update_slot(session, tenant.id, slot_id, data)
    await session.commit()
    return updated


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
