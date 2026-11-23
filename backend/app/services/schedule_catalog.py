"""Provider schedule, gallery, and delivery zones for the public landing."""

from datetime import time
from uuid import UUID

from fastapi import HTTPException, status
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.commerce import DeliveryZone, Quote, Reservation
from app.models.tenant import ServiceScheduleSlot, TenantPhoto
from app.schemas.quotes import PhotoIn, PhotoRead, SlotIn, SlotRead, ZoneIn, ZoneRead
from app.services.availability import day_name, slot_label, tenant_slots
from app.services.catalog_common import clean_money, clean_name, clean_optional, owned


def parse_clock(value: str) -> time:
    try:
        parsed = time.fromisoformat(value.strip())
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="La hora no es válida",
        )
    return parsed.replace(second=0, microsecond=0)


def parse_day(value: int) -> int:
    if value < 0 or value > 6:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="El día de la semana no es válido",
        )
    return value


def clean_photo_url(value: str) -> str:
    cleaned = value.strip()
    if not cleaned.startswith(("http://", "https://")):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="La foto debe ser una URL http o https",
        )
    if len(cleaned) > 2048:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="La URL es demasiado larga",
        )
    return cleaned


def slot_read(row: ServiceScheduleSlot) -> SlotRead:
    return SlotRead(
        id=row.id,
        day_of_week=row.day_of_week,
        day_name=day_name(row.day_of_week),
        start_time=f"{row.start_time:%H:%M}",
        end_time=f"{row.end_time:%H:%M}",
        label=slot_label(row.start_time, row.end_time),
        is_active=row.is_active,
    )


async def list_slot_reads(session: AsyncSession, tenant_id: UUID) -> list[SlotRead]:
    return [slot_read(row) for row in await tenant_slots(session, tenant_id)]


async def create_slot(session: AsyncSession, tenant_id: UUID, data: SlotIn) -> SlotRead:
    start = parse_clock(data.start_time)
    end = parse_clock(data.end_time)
    if end <= start:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="La hora de fin debe ser posterior a la de inicio",
        )
    row = ServiceScheduleSlot(
        tenant_id=tenant_id,
        day_of_week=parse_day(data.day_of_week),
        start_time=start,
        end_time=end,
        is_active=data.is_active,
    )
    session.add(row)
    await session.flush()
    return slot_read(row)


async def delete_slot(session: AsyncSession, tenant_id: UUID, slot_id: UUID) -> None:
    row = await owned(
        session,
        ServiceScheduleSlot,
        slot_id,
        tenant_id,
        "No se encontró el horario",
    )
    if await _slot_in_use(session, tenant_id, slot_id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Hay cotizaciones o reservaciones en ese horario",
        )
    await session.delete(row)


async def list_photos(session: AsyncSession, tenant_id: UUID) -> list[PhotoRead]:
    result = await session.exec(
        select(TenantPhoto).where(TenantPhoto.tenant_id == tenant_id)
    )
    rows = list(result.all())
    rows.sort(key=lambda row: (row.display_order, str(row.id)))
    return [
        PhotoRead(
            id=row.id,
            image_url=row.image_url,
            caption=row.caption,
            display_order=row.display_order,
        )
        for row in rows
    ]


async def create_photo(
    session: AsyncSession, tenant_id: UUID, data: PhotoIn
) -> PhotoRead:
    if data.display_order < 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="El orden de la foto no puede ser negativo",
        )
    row = TenantPhoto(
        tenant_id=tenant_id,
        image_url=clean_photo_url(data.image_url),
        caption=clean_optional(data.caption, limit=255),
        display_order=data.display_order,
    )
    session.add(row)
    await session.flush()
    return PhotoRead(
        id=row.id,
        image_url=row.image_url,
        caption=row.caption,
        display_order=row.display_order,
    )


async def delete_photo(session: AsyncSession, tenant_id: UUID, photo_id: UUID) -> None:
    row = await owned(
        session, TenantPhoto, photo_id, tenant_id, "No se encontró la foto"
    )
    await session.delete(row)


async def list_zones(session: AsyncSession, tenant_id: UUID) -> list[ZoneRead]:
    result = await session.exec(
        select(DeliveryZone).where(DeliveryZone.tenant_id == tenant_id)
    )
    rows = list(result.all())
    rows.sort(key=lambda row: row.zone_name.lower())
    return [
        ZoneRead(id=row.id, zone_name=row.zone_name, freight_cost=row.freight_cost)
        for row in rows
    ]


async def create_zone(session: AsyncSession, tenant_id: UUID, data: ZoneIn) -> ZoneRead:
    row = DeliveryZone(
        tenant_id=tenant_id,
        zone_name=clean_name(data.zone_name),
        freight_cost=clean_money(data.freight_cost, "El flete"),
    )
    session.add(row)
    await session.flush()
    return ZoneRead(id=row.id, zone_name=row.zone_name, freight_cost=row.freight_cost)


async def _slot_in_use(session: AsyncSession, tenant_id: UUID, slot_id: UUID) -> bool:
    quotes = await session.exec(select(Quote).where(Quote.tenant_id == tenant_id))
    if any(row.slot_id == slot_id for row in quotes.all()):
        return True
    reservations = await session.exec(
        select(Reservation).where(Reservation.tenant_id == tenant_id)
    )
    return any(row.slot_id == slot_id for row in reservations.all())
