"""Concurrent schedule blocks.

A date offers a ServiceScheduleSlot only while confirmed reservations that
touch that block stay below the tenant's max_concurrent_events_per_slot.
The travel buffer also counts a neighboring block when the gap between the
two is shorter than travel_buffer_minutes. Cancelled reservations do not count.
Weekday numbers match date.weekday(): 0 is Monday and 6 is Sunday.
"""

from datetime import date, time, timedelta
from uuid import UUID

from fastapi import HTTPException, status
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.commerce import Reservation
from app.models.enums import OperationStatus
from app.models.tenant import ServiceScheduleSlot, Tenant

DAY_NAMES = (
    "Lunes",
    "Martes",
    "Miércoles",
    "Jueves",
    "Viernes",
    "Sábado",
    "Domingo",
)
SHORT_DAYS = ("Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom")


def day_name(day: int) -> str:
    if 0 <= day <= 6:
        return DAY_NAMES[day]
    return ""


def slot_label(start: time, end: time) -> str:
    return f"{start:%H:%M}–{end:%H:%M}"


def upcoming_days(start: date, count: int = 14) -> list[date]:
    return [start + timedelta(days=offset) for offset in range(count)]


def _minutes(value: time) -> int:
    return value.hour * 60 + value.minute


def _gap_minutes(left: ServiceScheduleSlot, right: ServiceScheduleSlot) -> int:
    if _minutes(left.start_time) <= _minutes(right.start_time):
        earlier_end = _minutes(left.end_time)
        later_start = _minutes(right.start_time)
    else:
        earlier_end = _minutes(right.end_time)
        later_start = _minutes(left.start_time)
    return later_start - earlier_end


def slots_conflict(
    candidate: ServiceScheduleSlot,
    other: ServiceScheduleSlot,
    buffer_minutes: int,
) -> bool:
    if candidate.id == other.id:
        return True
    return _gap_minutes(candidate, other) < buffer_minutes


async def tenant_slots(
    session: AsyncSession, tenant_id: UUID
) -> list[ServiceScheduleSlot]:
    result = await session.exec(
        select(ServiceScheduleSlot).where(ServiceScheduleSlot.tenant_id == tenant_id)
    )
    rows = list(result.all())
    rows.sort(
        key=lambda row: (row.day_of_week, row.start_time, row.end_time, str(row.id))
    )
    return rows


async def open_reservations(
    session: AsyncSession, tenant_id: UUID, event_date: date
) -> list[Reservation]:
    result = await session.exec(
        select(Reservation).where(Reservation.tenant_id == tenant_id)
    )
    return [
        row
        for row in result.all()
        if row.event_date == event_date
        and row.operation_status != OperationStatus.CANCELLED
    ]


async def occupancy(
    session: AsyncSession,
    tenant: Tenant,
    event_date: date,
    candidate: ServiceScheduleSlot,
) -> int:
    slots = {row.id: row for row in await tenant_slots(session, tenant.id)}
    count = 0
    for reservation in await open_reservations(session, tenant.id, event_date):
        other = slots.get(reservation.slot_id)
        if other is not None and slots_conflict(
            candidate, other, tenant.travel_buffer_minutes
        ):
            count += 1
    return count


async def open_slots(
    session: AsyncSession, tenant: Tenant, event_date: date
) -> list[tuple[ServiceScheduleSlot, int]]:
    """Active blocks for that weekday that still have room. Past dates are closed."""
    if event_date < date.today() or not tenant.has_active_plan:
        return []
    available: list[tuple[ServiceScheduleSlot, int]] = []
    for slot in await tenant_slots(session, tenant.id):
        if not slot.is_active or slot.day_of_week != event_date.weekday():
            continue
        used = await occupancy(session, tenant, event_date, slot)
        remaining = tenant.max_concurrent_events_per_slot - used
        if remaining > 0:
            available.append((slot, remaining))
    return available


async def assert_slot_open(
    session: AsyncSession,
    tenant: Tenant,
    event_date: date,
    slot_id: UUID,
) -> ServiceScheduleSlot:
    slot = await session.get(ServiceScheduleSlot, slot_id)
    if slot is None or slot.tenant_id != tenant.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No se encontró el horario",
        )
    if event_date < date.today():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="La fecha ya pasó",
        )
    if slot.day_of_week != event_date.weekday():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="El horario no corresponde a ese día",
        )
    if not slot.is_active:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ese horario no está activo",
        )
    used = await occupancy(session, tenant, event_date, slot)
    if used >= tenant.max_concurrent_events_per_slot:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ese horario ya no tiene lugar",
        )
    return slot
