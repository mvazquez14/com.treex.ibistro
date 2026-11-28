import uuid
from datetime import time
from decimal import Decimal

from sqlalchemy import Column, Float, Index, Integer, text
from sqlmodel import Field, SQLModel

from app.models.columns import fk, jsonb_column, money_column, text_column, uuid_pk


def _default_modules() -> list[str]:
    return ["catering_core", "concierge_bot", "pos_lite"]


class Tenant(SQLModel, table=True):
    __tablename__ = "tenant"
    __table_args__ = (
        Index(
            "uq_tenant_rfc_present",
            "rfc",
            unique=True,
            postgresql_where=text("rfc <> ''"),
        ),
        Index(
            "uq_tenant_whatsapp_present",
            "whatsapp_phone",
            unique=True,
            postgresql_where=text("whatsapp_phone <> ''"),
        ),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, sa_column=uuid_pk())
    nuna_org_id: str = Field(max_length=128, unique=True, index=True)
    slug: str = Field(max_length=80, unique=True, index=True)
    business_name: str = Field(max_length=255)
    rfc: str = Field(default="", max_length=20)
    address: str = Field(default="", max_length=500)
    logo_url: str | None = Field(default=None, max_length=2048)
    category_tags: list[str] = Field(
        default_factory=list,
        sa_column=jsonb_column("'[]'::jsonb"),
    )
    min_guests: int = Field(
        default=20, sa_column=Column(Integer, nullable=False, server_default="20")
    )
    max_guests: int = Field(
        default=300, sa_column=Column(Integer, nullable=False, server_default="300")
    )
    accepts_cash: bool = Field(default=True)
    accepts_transfer: bool = Field(default=True)
    transfer_instructions: str = Field(default="", sa_column=text_column())
    whatsapp_phone: str = Field(default="", max_length=20)
    contact_phone: str = Field(default="", max_length=20)
    show_prices_public: bool = Field(default=True)
    default_tax_rate: float = Field(
        default=0.16,
        sa_column=Column(Float, nullable=False, server_default="0.16"),
    )
    deposit_percentage: float = Field(
        default=50.0,
        sa_column=Column(Float, nullable=False, server_default="50"),
    )
    waiter_ratio: int = Field(
        default=20, sa_column=Column(Integer, nullable=False, server_default="20")
    )
    waiter_cost_per_event: Decimal = Field(
        default=Decimal("0.00"),
        sa_column=money_column(),
    )
    max_concurrent_events_per_slot: int = Field(
        default=1,
        sa_column=Column(Integer, nullable=False, server_default="1"),
    )
    travel_buffer_minutes: int = Field(
        default=60,
        sa_column=Column(Integer, nullable=False, server_default="60"),
    )
    service_duration_minutes: int = Field(
        default=120,
        sa_column=Column(Integer, nullable=False, server_default="120"),
    )
    has_active_plan: bool = Field(default=False)
    onboarding_completed: bool = Field(default=False)
    is_verified_concierge: bool = Field(default=False)
    concierge_priority_score: int = Field(
        default=100,
        sa_column=Column(Integer, nullable=False, server_default="100"),
    )
    enabled_modules: list[str] = Field(
        default_factory=_default_modules,
        sa_column=jsonb_column(
            '\'["catering_core", "concierge_bot", "pos_lite"]\'::jsonb'
        ),
    )


class TenantPhoto(SQLModel, table=True):
    __tablename__ = "tenant_photo"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, sa_column=uuid_pk())
    tenant_id: uuid.UUID = Field(sa_column=fk("tenant.id"))
    image_url: str = Field(max_length=2048)
    caption: str | None = Field(default=None, max_length=255)
    display_order: int = Field(default=0)


class ServiceScheduleSlot(SQLModel, table=True):
    __tablename__ = "service_schedule_slot"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, sa_column=uuid_pk())
    tenant_id: uuid.UUID = Field(sa_column=fk("tenant.id"))
    day_of_week: int = Field(ge=0, le=6)
    start_time: time
    end_time: time
    is_active: bool = Field(default=True)


class ServiceCategory(SQLModel, table=True):
    __tablename__ = "service_category"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, sa_column=uuid_pk())
    name: str = Field(max_length=80, unique=True)
    slug: str = Field(max_length=80, unique=True)
    icon: str = Field(default="", max_length=80)
    is_active: bool = Field(default=True)
