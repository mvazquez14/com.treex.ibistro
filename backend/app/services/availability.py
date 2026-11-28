"""Concurrent event windows.

A start time is offered every 30 minutes inside an active day window when the
service itself ends at or before closing. Each booking occupies
[start, start + service_duration_minutes + travel_buffer_minutes). A start is
open only while overlapping active events stay below
max_concurrent_events_per_slot. Cancelled reservations do not count. Rows
without event_start use their schedule window's start. Weekday numbers match
date.weekday(): 0 is Monday and 6 is Sunday.
"""

import calendar
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


def _clock(minutes: int) -> time:
    return time(hour=minutes // 60, minute=minutes % 60)


def service_window(start: time, service_minutes: int, travel_minutes: int) -> tuple[int, int]:
    begin = _minutes(start)
    return begin, begin + service_minutes + max(0, travel_minutes)


def windows_overlap(left: tuple[int, int], right: tuple[int, int]) -> bool:
    return left[0] < right[1] and right[0] < left[1]


def candidate_starts(slot: ServiceScheduleSlot, service_minutes: int) -> list[time]:
    open_at = _minutes(slot.start_time)
    close_at = _minutes(slot.end_time)
    starts: list[time] = []
    cursor = open_at
    while cursor + service_minutes <= close_at:
        starts.append(_clock(cursor))
        cursor += 30
    return starts


def fits_before_close(slot: ServiceScheduleSlot, start: time, service_minutes: int) -> bool:
    begin = _minutes(start)
    return _minutes(slot.start_time) <= begin and begin + service_minutes <= _minutes(slot.end_time)


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


def clock_text(value: time | None) -> str:
    if value is None:
        return ""
    return f"{value:%H:%M}"


def end_clock(start: time, service_minutes: int) -> time:
    total = _minutes(start) + max(0, service_minutes)
    return _clock(total % (24 * 60))


async def occupancy_at(
    session: AsyncSession,
    tenant: Tenant,
    event_date: date,
    start: time,
    ignore_id: UUID | None = None,
) -> int:
    slots = {row.id: row for row in await tenant_slots(session, tenant.id)}
    service = tenant.service_duration_minutes
    travel = tenant.travel_buffer_minutes
    candidate = service_window(start, service, travel)
    count = 0
    for reservation in await open_reservations(session, tenant.id, event_date):
        if ignore_id is not None and reservation.id == ignore_id:
            continue
        other = slots.get(reservation.slot_id)
        begin = reservation.event_start or (other.start_time if other is not None else None)
        if begin is None:
            continue
        occupied = service_window(begin, service, travel)
        if windows_overlap(candidate, occupied):
            count += 1
    return count


async def open_slots(
    session: AsyncSession,
    tenant: Tenant,
    event_date: date,
    ignore_id: UUID | None = None,
) -> list[tuple[ServiceScheduleSlot, time, int]]:
    """Start times that still fit before close and under the concurrent cap."""
    if event_date < date.today() or not tenant.has_active_plan:
        return []
    available: list[tuple[ServiceScheduleSlot, time, int]] = []
    service = tenant.service_duration_minutes
    for slot in await tenant_slots(session, tenant.id):
        if not slot.is_active or slot.day_of_week != event_date.weekday():
            continue
        for start in candidate_starts(slot, service):
            used = await occupancy_at(session, tenant, event_date, start, ignore_id)
            remaining = tenant.max_concurrent_events_per_slot - used
            if remaining > 0:
                available.append((slot, start, remaining))
    return available


async def assert_slot_open(
    session: AsyncSession,
    tenant: Tenant,
    event_date: date,
    slot_id: UUID,
    start: time | None = None,
    ignore_id: UUID | None = None,
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
    chosen = start or slot.start_time
    if not fits_before_close(slot, chosen, tenant.service_duration_minutes):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="El servicio no cabe antes del cierre",
        )
    used = await occupancy_at(session, tenant, event_date, chosen, ignore_id)
    if used >= tenant.max_concurrent_events_per_slot:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ese horario ya no tiene lugar",
        )
    return slot


def parse_month(value: str) -> tuple[int, int]:
    try:
        year_text, month_text = value.split("-", maxsplit=1)
        year = int(year_text)
        month = int(month_text)
    except ValueError:
        year, month = 0, 0
    if year < 2000 or month < 1 or month > 12:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="El mes no es válido",
        )
    return year, month


async def month_availability(
    session: AsyncSession, tenant: Tenant, year: int, month: int
) -> list[tuple[date, str, list[tuple[ServiceScheduleSlot, time]]]]:
    """Each day is available, full, or closed, with the bookable start times."""
    last_day = calendar.monthrange(year, month)[1]
    slots = await tenant_slots(session, tenant.id)
    described: list[tuple[date, str, list[tuple[ServiceScheduleSlot, time]]]] = []
    for day_number in range(1, last_day + 1):
        current = date(year, month, day_number)
        windows = [
            slot
            for slot in slots
            if slot.is_active and slot.day_of_week == current.weekday()
        ]
        bookable = [
            start
            for slot in windows
            for start in candidate_starts(slot, tenant.service_duration_minutes)
        ]
        if current < date.today() or not tenant.has_active_plan or not bookable:
            described.append((current, "closed", []))
            continue
        opened = await open_slots(session, tenant, current)
        if not opened:
            described.append((current, "full", []))
            continue
        described.append(
            (
                current,
                "available",
                [(slot, start) for slot, start, _remaining in opened],
            )
        )
    return described
