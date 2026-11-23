"""Contracts for the Orion concierge API."""

from datetime import date
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.enums import LeadSource
from app.schemas.catalog import QuoteExtraIn
from app.schemas.quotes import PublicExtra, PublicPackage, PublicQuoteOut, PublicSlot


class ConciergeCategory(BaseModel):
    id: UUID
    name: str
    slug: str
    icon: str


class ConciergeProvider(BaseModel):
    id: UUID
    slug: str
    business_name: str
    concierge_priority_score: int
    landing_url: str
    slots: list[PublicSlot]


class ConciergeDay(BaseModel):
    event_date: date
    slots: list[PublicSlot]


class ConciergeAvailability(BaseModel):
    provider_id: UUID
    business_name: str
    days: list[ConciergeDay]


class ConciergeMenu(BaseModel):
    provider_id: UUID
    business_name: str
    show_prices: bool
    packages: list[PublicPackage]
    extras: list[PublicExtra]


class ConciergeQuoteIn(BaseModel):
    provider_id: UUID
    source: LeadSource
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


ConciergeQuoteOut = PublicQuoteOut
