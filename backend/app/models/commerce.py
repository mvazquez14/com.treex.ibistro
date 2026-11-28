import uuid
from datetime import date, datetime, time
from decimal import Decimal
from typing import Any

from sqlalchemy import Column, Date, Integer, Time
from sqlmodel import Field, SQLModel

from app.models.columns import (
    created_at_column,
    enum_column,
    fk,
    jsonb_column,
    money_column,
    text_column,
    utcnow,
    uuid_pk,
)
from app.models.enums import (
    LeadSource,
    OperationStatus,
    PaymentMethod,
    PaymentStatus,
    QuoteStatus,
)


class DeliveryZone(SQLModel, table=True):
    __tablename__ = "delivery_zone"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, sa_column=uuid_pk())
    tenant_id: uuid.UUID = Field(sa_column=fk("tenant.id"))
    zone_name: str = Field(max_length=255)
    freight_cost: Decimal = Field(sa_column=money_column())


class Lead(SQLModel, table=True):
    __tablename__ = "lead"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, sa_column=uuid_pk())
    tenant_id: uuid.UUID = Field(sa_column=fk("tenant.id"))
    full_name: str = Field(max_length=255)
    phone: str = Field(max_length=20)
    whatsapp_phone: str = Field(max_length=20)
    email: str | None = Field(default=None, max_length=255)
    source: LeadSource = Field(sa_column=enum_column(LeadSource, "lead_source"))


class Quote(SQLModel, table=True):
    __tablename__ = "quote"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, sa_column=uuid_pk())
    tenant_id: uuid.UUID = Field(sa_column=fk("tenant.id"))
    lead_id: uuid.UUID = Field(sa_column=fk("lead.id"))
    package_id: uuid.UUID = Field(sa_column=fk("catering_package.id"))
    delivery_zone_id: uuid.UUID | None = Field(
        default=None,
        sa_column=fk("delivery_zone.id", nullable=True, ondelete="SET NULL"),
    )
    event_date: date = Field(sa_column=Column(Date, nullable=False))
    event_start: time | None = Field(default=None, sa_column=Column(Time, nullable=True))
    end_time: time | None = Field(default=None, sa_column=Column(Time, nullable=True))
    slot_id: uuid.UUID = Field(sa_column=fk("service_schedule_slot.id"))
    venue_address: str = Field(max_length=500)
    guest_count: int = Field(sa_column=Column(Integer, nullable=False))
    waiters_count: int = Field(sa_column=Column(Integer, nullable=False))
    selected_options_json: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=jsonb_column("'{}'::jsonb"),
    )
    selected_extras_json: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=jsonb_column("'{}'::jsonb"),
    )
    selected_equipment_json: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=jsonb_column("'{}'::jsonb"),
    )
    subtotal: Decimal = Field(sa_column=money_column())
    discount_amount: Decimal = Field(default=Decimal("0.00"), sa_column=money_column())
    tax_amount: Decimal = Field(default=Decimal("0.00"), sa_column=money_column())
    total_amount: Decimal = Field(sa_column=money_column())
    estimated_cogs: Decimal = Field(sa_column=money_column())
    status: QuoteStatus = Field(
        default=QuoteStatus.PENDING_REVIEW,
        sa_column=enum_column(QuoteStatus, "quote_status"),
    )
    public_token: uuid.UUID = Field(default_factory=uuid.uuid4, unique=True, index=True)
    special_requests: str | None = Field(
        default=None, sa_column=text_column(nullable=True)
    )
    created_at: datetime = Field(default_factory=utcnow, sa_column=created_at_column())


class Reservation(SQLModel, table=True):
    __tablename__ = "reservation"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, sa_column=uuid_pk())
    tenant_id: uuid.UUID = Field(sa_column=fk("tenant.id"))
    quote_id: uuid.UUID | None = Field(
        default=None,
        sa_column=fk("quote.id", nullable=True, ondelete="SET NULL"),
    )
    customer_name: str = Field(max_length=255)
    customer_phone: str = Field(max_length=20)
    venue_address: str = Field(max_length=500)
    event_date: date = Field(sa_column=Column(Date, nullable=False, index=True))
    event_start: time | None = Field(default=None, sa_column=Column(Time, nullable=True))
    end_time: time | None = Field(default=None, sa_column=Column(Time, nullable=True))
    slot_id: uuid.UUID = Field(sa_column=fk("service_schedule_slot.id"))
    guest_count: int = Field(sa_column=Column(Integer, nullable=False))
    total_amount: Decimal = Field(sa_column=money_column())
    paid_amount: Decimal = Field(default=Decimal("0.00"), sa_column=money_column())
    payment_status: PaymentStatus = Field(
        default=PaymentStatus.UNPAID,
        sa_column=enum_column(PaymentStatus, "payment_status"),
    )
    operation_status: OperationStatus = Field(
        default=OperationStatus.CONFIRMED,
        sa_column=enum_column(OperationStatus, "operation_status"),
    )
    special_requests: str | None = Field(
        default=None, sa_column=text_column(nullable=True)
    )
    change_log: list[Any] = Field(
        default_factory=list,
        sa_column=jsonb_column("'[]'::jsonb"),
    )
    created_at: datetime = Field(default_factory=utcnow, sa_column=created_at_column())


class PaymentReceipt(SQLModel, table=True):
    __tablename__ = "payment_receipt"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, sa_column=uuid_pk())
    tenant_id: uuid.UUID = Field(sa_column=fk("tenant.id"))
    reservation_id: uuid.UUID = Field(sa_column=fk("reservation.id"))
    amount: Decimal = Field(sa_column=money_column())
    payment_method: PaymentMethod = Field(
        sa_column=enum_column(PaymentMethod, "payment_method")
    )
    receipt_file_url: str | None = Field(default=None, max_length=2048)
    is_verified: bool = Field(default=False)
    uploaded_at: datetime = Field(default_factory=utcnow, sa_column=created_at_column())


class POSOrder(SQLModel, table=True):
    __tablename__ = "pos_order"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, sa_column=uuid_pk())
    tenant_id: uuid.UUID = Field(sa_column=fk("tenant.id"))
    warehouse_id: uuid.UUID = Field(sa_column=fk("warehouse.id"))
    reservation_id: uuid.UUID | None = Field(
        default=None,
        sa_column=fk("reservation.id", nullable=True, ondelete="SET NULL"),
    )
    items_json: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=jsonb_column("'{}'::jsonb"),
    )
    subtotal: Decimal = Field(sa_column=money_column())
    tax_amount: Decimal = Field(sa_column=money_column())
    total_amount: Decimal = Field(sa_column=money_column())
    payment_method: PaymentMethod = Field(
        sa_column=enum_column(PaymentMethod, "payment_method")
    )
    created_at: datetime = Field(default_factory=utcnow, sa_column=created_at_column())
