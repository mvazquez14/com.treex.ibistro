"""Contracts for the public landing and the quotes desk."""

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from app.models.enums import PricingType, QuoteStatus
from app.schemas.catalog import ExtraRead, PackageRead, QuoteExtraIn


class SlotIn(BaseModel):
    day_of_week: int = Field(ge=0, le=6)
    start_time: str
    end_time: str
    is_active: bool = True


class SlotRead(BaseModel):
    id: UUID
    day_of_week: int
    day_name: str
    start_time: str
    end_time: str
    label: str
    is_active: bool


class PhotoIn(BaseModel):
    image_url: str
    caption: str | None = None
    display_order: int = 0


class PhotoRead(BaseModel):
    id: UUID
    image_url: str
    caption: str | None
    display_order: int


class ZoneIn(BaseModel):
    zone_name: str
    freight_cost: Decimal


class ZoneRead(BaseModel):
    id: UUID
    zone_name: str
    freight_cost: Decimal


class CalendarDay(BaseModel):
    iso: str
    label: str


class CategoryChip(BaseModel):
    id: UUID
    name: str
    icon: str = ""


class LandingPage(BaseModel):
    slug: str
    tenant_id: UUID
    business_name: str
    rfc: str
    address: str
    logo_url: str | None
    categories: list[CategoryChip]
    tags: list[str]
    photos: list[PhotoRead]
    schedule: list[SlotRead]
    packages: list[PackageRead]
    extras: list[ExtraRead]
    zones: list[ZoneRead]
    days: list[CalendarDay]
    show_prices: bool
    available: bool
    concierge_url: str
    min_guests: int
    max_guests: int
    service_duration_minutes: int = 120


class PublicOption(BaseModel):
    recipe_id: UUID
    recipe_name: str
    extra_price_per_guest: Decimal | None = None


class PublicGroup(BaseModel):
    id: UUID
    group_name: str
    min_choices: int
    max_choices: int
    is_fixed: bool
    options: list[PublicOption]


class PublicPackage(BaseModel):
    id: UUID
    category_id: UUID
    category_name: str
    name: str
    description: str
    photo_url: str | None = None
    min_guests: int
    base_price_per_guest: Decimal | None = None
    groups: list[PublicGroup]


class PublicExtra(BaseModel):
    id: UUID
    name: str
    pricing_type: PricingType
    unit_price: Decimal | None = None
    category_ids: list[UUID] = Field(default_factory=list)


class PublicZone(BaseModel):
    id: UUID
    zone_name: str
    freight_cost: Decimal | None = None


class PublicProfile(BaseModel):
    slug: str
    business_name: str
    logo_url: str | None
    available: bool
    show_prices: bool
    message: str | None = None
    categories: list[str]
    photos: list[PhotoRead]
    schedule: list[SlotRead]
    packages: list[PublicPackage]
    extras: list[PublicExtra]
    zones: list[PublicZone]
    concierge_url: str


class AvailabilityStart(BaseModel):
    slot_id: UUID
    start: str


class AvailabilityDay(BaseModel):
    date: date
    weekday: int
    status: str
    available_slots: list[str]
    bookings: list[AvailabilityStart] = Field(default_factory=list)


class MonthAvailability(BaseModel):
    month: str
    service_duration_minutes: int
    days: list[AvailabilityDay]


class PublicSlot(BaseModel):
    id: UUID
    label: str
    start_time: str
    end_time: str
    remaining: int


class PublicQuoteIn(BaseModel):
    package_id: UUID
    event_date: date
    slot_id: UUID
    guest_count: int = Field(ge=1)
    full_name: str
    phone: str
    whatsapp_phone: str
    email: str | None = None
    venue_address: str
    special_requests: str | None = None
    selected_options: dict[UUID, list[UUID]] = Field(default_factory=dict)
    extras: list[QuoteExtraIn] = Field(default_factory=list)
    delivery_zone_id: UUID | None = None
    start_time: str | None = None

    @field_validator("email", "special_requests", "start_time", mode="before")
    @classmethod
    def empty_text_is_missing(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("delivery_zone_id", mode="before")
    @classmethod
    def empty_zone_is_missing(cls, value: object) -> object:
        if value == "":
            return None
        return value


class PricePreview(BaseModel):
    show_prices: bool
    message: str
    package_name: str
    waiters_count: int
    subtotal: Decimal | None = None
    discount_amount: Decimal | None = None
    tax_amount: Decimal | None = None
    total_amount: Decimal | None = None


class PublicQuoteOut(BaseModel):
    id: UUID
    public_token: UUID
    status: QuoteStatus
    show_prices: bool
    message: str
    package_name: str
    event_date: date
    slot_label: str
    guest_count: int
    subtotal: Decimal | None = None
    discount_amount: Decimal | None = None
    tax_amount: Decimal | None = None
    total_amount: Decimal | None = None
    tracking_url: str
    variant_summary: str = ""
    extras_summary: str = ""
    client_whatsapp_url: str = ""


class QuoteLine(BaseModel):
    name: str
    quantity: str


class QuoteChoice(BaseModel):
    group_id: UUID
    recipe_id: UUID
    quantity: int


class QuoteExtraPick(BaseModel):
    extra_id: UUID
    name: str
    quantity: str


class QuoteAdjustIn(BaseModel):
    discount_amount: Decimal = Decimal("0")
    apply_tax: bool = True
    tax_rate: Decimal | None = None
    guest_count: int | None = Field(default=None, ge=1)
    package_id: UUID | None = None
    slot_id: UUID | None = None
    start_time: str | None = None
    event_date: date | None = None
    selected_options: dict[UUID, list[UUID]] | None = None
    extras: list[QuoteExtraIn] | None = None
    manual_total: Decimal | None = None


class ScheduleChoice(BaseModel):
    event_date: date
    slot_id: UUID
    start_time: str


class QuoteDetail(BaseModel):
    id: UUID
    public_token: UUID
    status: QuoteStatus
    status_label: str
    lead_name: str
    phone: str
    whatsapp_phone: str
    email: str | None
    package_id: UUID
    slot_id: UUID
    package_name: str
    folio: str = ""
    category_name: str = ""
    whatsapp_url: str = ""
    variants: list[QuoteLine] = Field(default_factory=list)
    extras: list[QuoteLine] = Field(default_factory=list)
    choices: list[QuoteChoice] = Field(default_factory=list)
    extra_picks: list[QuoteExtraPick] = Field(default_factory=list)
    event_date: date
    slot_label: str
    start_time: str = ""
    end_time: str = ""
    venue_address: str
    guest_count: int
    waiters_count: int
    subtotal: Decimal
    discount_amount: Decimal
    tax_amount: Decimal
    total_amount: Decimal
    estimated_cogs: Decimal
    special_requests: str | None
    reservation_id: UUID | None
    can_rebook: bool = False
    apply_tax: bool
    tax_rate: Decimal
    variant_summary: str = ""
    created_at: datetime


class QuotesScreen(BaseModel):
    quotes: list[QuoteDetail]
    slots: list[SlotRead]
    photos: list[PhotoRead]
    zones: list[ZoneRead]
    tax_rate: float
    slug: str
    business_name: str
