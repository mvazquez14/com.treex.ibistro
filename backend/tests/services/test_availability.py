"""30-minute starts: a booking occupies service time plus the travel buffer."""

from datetime import date, time, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.models import OperationStatus, Reservation, ServiceScheduleSlot, Tenant
from app.services.availability import assert_slot_open, day_name, open_slots
from tests.memory_db import MemorySession


def _tenant(**overrides: object) -> Tenant:
    values: dict[str, object] = {
        "nuna_org_id": "org-slots",
        "slug": "slots-demo",
        "business_name": "Slots Demo",
        "has_active_plan": True,
        "max_concurrent_events_per_slot": 1,
        "travel_buffer_minutes": 60,
        "service_duration_minutes": 120,
        "min_guests": 1,
        "max_guests": 300,
    }
    values.update(overrides)
    return Tenant(**values)  # type: ignore[arg-type]


def _slot(
    tenant: Tenant, day: date, start: time, end: time, *, active: bool = True
) -> ServiceScheduleSlot:
    return ServiceScheduleSlot(
        tenant_id=tenant.id,
        day_of_week=day.weekday(),
        start_time=start,
        end_time=end,
        is_active=active,
    )


def _reservation(
    tenant: Tenant,
    slot: ServiceScheduleSlot,
    day: date,
    *,
    status: OperationStatus = OperationStatus.CONFIRMED,
) -> Reservation:
    return Reservation(
        tenant_id=tenant.id,
        customer_name="Ana",
        customer_phone="+5213311111111",
        venue_address="Calle 1",
        event_date=day,
        slot_id=slot.id,
        guest_count=20,
        total_amount=Decimal("100.00"),
        operation_status=status,
    )


async def test_one_confirmed_reservation_closes_the_only_seat(
    memory_db: MemorySession,
) -> None:
    day = date.today() + timedelta(days=1)
    tenant = _tenant()
    slot = _slot(tenant, day, time(10, 0), time(12, 0))
    memory_db.add(tenant)
    memory_db.add(slot)
    memory_db.add(_reservation(tenant, slot, day))

    assert await open_slots(memory_db, tenant, day) == []  # type: ignore[arg-type]
    with pytest.raises(HTTPException) as exc:
        await assert_slot_open(memory_db, tenant, day, slot.id)  # type: ignore[arg-type]
    assert exc.value.status_code == 409
    assert exc.value.detail == "Ese horario ya no tiene lugar"


async def test_cancelled_reservation_does_not_fill_the_slot(
    memory_db: MemorySession,
) -> None:
    day = date.today() + timedelta(days=1)
    tenant = _tenant()
    slot = _slot(tenant, day, time(10, 0), time(12, 0))
    memory_db.add(tenant)
    memory_db.add(slot)
    memory_db.add(_reservation(tenant, slot, day, status=OperationStatus.CANCELLED))

    opened = await open_slots(memory_db, tenant, day)  # type: ignore[arg-type]
    assert [(row.id, start) for row, start, _remaining in opened] == [
        (slot.id, time(10, 0))
    ]
    assert opened[0][2] == 1


async def test_two_seats_leave_room_for_a_second_event(
    memory_db: MemorySession,
) -> None:
    day = date.today() + timedelta(days=1)
    tenant = _tenant(max_concurrent_events_per_slot=2)
    slot = _slot(tenant, day, time(10, 0), time(12, 0))
    memory_db.add(tenant)
    memory_db.add(slot)
    memory_db.add(_reservation(tenant, slot, day))

    opened = await open_slots(memory_db, tenant, day)  # type: ignore[arg-type]
    assert opened[0][2] == 1
    assert opened[0][1] == time(10, 0)

    memory_db.add(_reservation(tenant, slot, day))
    assert await open_slots(memory_db, tenant, day) == []  # type: ignore[arg-type]


async def test_travel_buffer_blocks_a_neighbor_and_keeps_a_later_block(
    memory_db: MemorySession,
) -> None:
    day = date.today() + timedelta(days=1)
    tenant = _tenant(travel_buffer_minutes=60)
    morning = _slot(tenant, day, time(10, 0), time(12, 0))
    noon = _slot(tenant, day, time(12, 0), time(13, 0))
    afternoon = _slot(tenant, day, time(15, 0), time(17, 0))
    memory_db.add(tenant)
    memory_db.add(morning)
    memory_db.add(noon)
    memory_db.add(afternoon)
    memory_db.add(_reservation(tenant, morning, day))

    opened = await open_slots(memory_db, tenant, day)  # type: ignore[arg-type]
    assert [row.id for row, _start, _remaining in opened] == [afternoon.id]

    memory_db.rows[Reservation].clear()
    memory_db.add(_reservation(tenant, afternoon, day))
    opened = await open_slots(memory_db, tenant, day)  # type: ignore[arg-type]
    opened_ids = [row.id for row, _start, _remaining in opened]
    assert morning.id in opened_ids
    assert afternoon.id not in opened_ids
    assert noon.id not in opened_ids


async def test_past_inactive_and_wrong_weekday_are_rejected(
    memory_db: MemorySession,
) -> None:
    tenant = _tenant()
    yesterday = date.today() - timedelta(days=1)
    tomorrow = date.today() + timedelta(days=1)
    past = _slot(tenant, yesterday, time(10, 0), time(12, 0))
    inactive = _slot(tenant, tomorrow, time(10, 0), time(12, 0), active=False)
    other_day = ServiceScheduleSlot(
        tenant_id=tenant.id,
        day_of_week=(tomorrow.weekday() + 1) % 7,
        start_time=time(10, 0),
        end_time=time(12, 0),
        is_active=True,
    )
    memory_db.add(tenant)
    memory_db.add(past)
    memory_db.add(inactive)
    memory_db.add(other_day)

    assert await open_slots(memory_db, tenant, yesterday) == []  # type: ignore[arg-type]
    with pytest.raises(HTTPException) as past_error:
        await assert_slot_open(memory_db, tenant, yesterday, past.id)  # type: ignore[arg-type]
    assert past_error.value.detail == "La fecha ya pasó"

    with pytest.raises(HTTPException) as inactive_error:
        await assert_slot_open(memory_db, tenant, tomorrow, inactive.id)  # type: ignore[arg-type]
    assert inactive_error.value.detail == "Ese horario no está activo"

    with pytest.raises(HTTPException) as weekday_error:
        await assert_slot_open(memory_db, tenant, tomorrow, other_day.id)  # type: ignore[arg-type]
    assert weekday_error.value.detail == "El horario no corresponde a ese día"
    assert await open_slots(memory_db, tenant, tomorrow) == []  # type: ignore[arg-type]
    assert day_name(9) == ""
    with pytest.raises(HTTPException) as missing:
        await assert_slot_open(memory_db, tenant, tomorrow, uuid4())  # type: ignore[arg-type]
    assert missing.value.status_code == 404


async def test_long_window_offers_starts_every_thirty_minutes(
    memory_db: MemorySession,
) -> None:
    day = date.today() + timedelta(days=1)
    tenant = _tenant()
    slot = _slot(tenant, day, time(10, 0), time(14, 0))
    memory_db.add(tenant)
    memory_db.add(slot)

    opened = await open_slots(memory_db, tenant, day)  # type: ignore[arg-type]
    assert [start for _slot, start, _remaining in opened] == [
        time(10, 0),
        time(10, 30),
        time(11, 0),
        time(11, 30),
        time(12, 0),
    ]
    with pytest.raises(HTTPException) as late:
        await assert_slot_open(memory_db, tenant, day, slot.id, time(12, 30))  # type: ignore[arg-type]
    assert late.value.detail == "El servicio no cabe antes del cierre"
