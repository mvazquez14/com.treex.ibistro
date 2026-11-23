"""Public quotes, dashboard negotiation, and conversion to a reservation."""

import logging
import math
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any
from urllib.parse import quote
from uuid import UUID

from fastapi import HTTPException, status
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.models.commerce import DeliveryZone, Lead, Quote, Reservation
from app.models.enums import (
    LeadSource,
    OperationStatus,
    PaymentStatus,
    PricingType,
    QuoteStatus,
)
from app.models.equipment import EquipmentAsset, PackageEquipmentRule
from app.models.tenant import ServiceScheduleSlot, Tenant
from app.schemas.catalog import ExtraRead, PackageRead, QuoteExtraIn, QuoteIn
from app.schemas.quotes import (
    CalendarDay,
    CategoryChip,
    LandingPage,
    PricePreview,
    PublicExtra,
    PublicGroup,
    PublicOption,
    PublicPackage,
    PublicProfile,
    PublicQuoteIn,
    PublicQuoteOut,
    PublicSlot,
    PublicZone,
    QuoteAdjustIn,
    QuoteDetail,
    QuotesScreen,
    ZoneRead,
)
from app.services.availability import (
    SHORT_DAYS,
    assert_slot_open,
    open_reservations,
    open_slots,
    slot_label,
    upcoming_days,
)
from app.services.catalog_common import (
    clean_email,
    clean_money,
    clean_name,
    clean_phone,
    clean_text,
    owned,
)
from app.services.cost_engine import (
    CostError,
    IngredientNeed,
    as_money,
    equipment_units,
)
from app.services.inventory_service import commit_recipe_explosion
from app.services.menu_catalog import list_extras, list_packages, quote_for_package
from app.services.pdf_quote import QuoteDocument, render_quote_pdf
from app.services.schedule_catalog import list_photos, list_slot_reads, list_zones
from app.utils import render_email_template, send_email

logger = logging.getLogger(__name__)

HIDDEN_PRICE = "Cotización lista para revisión personalizada"
UNAVAILABLE = "Proveedor no disponible temporalmente"
STATUS_LABELS = {
    QuoteStatus.PENDING_REVIEW: "En revisión",
    QuoteStatus.SENT_TO_CLIENT: "Enviada al cliente",
    QuoteStatus.NEGOTIATING: "En negociación",
    QuoteStatus.APPROVED: "Aprobada",
    QuoteStatus.REJECTED: "Rechazada",
}


@dataclass(frozen=True)
class PricedEvent:
    package_name: str
    package_price: Decimal
    extras: tuple[dict[str, str], ...]
    options: tuple[dict[str, str], ...]
    equipment: tuple[dict[str, str], ...]
    freight: Decimal
    freight_name: str
    waiter_cost: Decimal
    waiters: int
    subtotal: Decimal
    discount: Decimal
    tax: Decimal
    total: Decimal
    cogs: Decimal
    explosion: tuple[IngredientNeed, ...]
    slot_label: str


def wa_link(phone: str, text: str) -> str:
    digits = phone.strip().lstrip("+")
    if not digits:
        return ""
    return f"https://wa.me/{digits}?text={quote(text, safe=':,')}"


def concierge_url(tenant: Tenant) -> str:
    return wa_link(
        settings.IBISTRO_CONCIERGE_PHONE,
        f"Hola iBistro, me interesa cotizar con provider_id:{tenant.id}",
    )


def require_bookable(tenant: Tenant) -> None:
    if not tenant.has_active_plan:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=UNAVAILABLE)


def require_phone(value: str) -> str:
    phone = clean_phone(value)
    if not phone:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Indica el teléfono en formato internacional, por ejemplo +523312345678",
        )
    return phone


def waiter_count(guests: int, ratio: int) -> int:
    if guests < 1:
        return 0
    safe_ratio = ratio if ratio > 0 else 1
    return math.ceil(guests / safe_ratio)


def money_text(value: Decimal) -> str:
    return f"{as_money(value):.2f}"


def clean_rate(value: Decimal) -> Decimal:
    if value < 0 or value > 1:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="La tasa de IVA no es válida",
        )
    return value


def quote_totals(
    subtotal: Decimal, discount: Decimal, rate: Decimal, apply_tax: bool
) -> tuple[Decimal, Decimal, Decimal]:
    discount = clean_money(discount, "El descuento")
    if discount > subtotal:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="El descuento no puede ser mayor que el subtotal",
        )
    taxable = as_money(subtotal - discount)
    tax = as_money(taxable * rate) if apply_tax else Decimal("0.00")
    return discount, tax, as_money(taxable + tax)


async def tenant_by_slug(session: AsyncSession, slug: str) -> Tenant:
    result = await session.exec(select(Tenant).where(Tenant.slug == slug))
    tenant = result.first()
    if tenant is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No se encontró el proveedor",
        )
    return tenant


async def landing_page(session: AsyncSession, slug: str) -> LandingPage:
    tenant = await tenant_by_slug(session, slug)
    packages = [
        package
        for package in await list_packages(session, tenant.id)
        if package.is_active
    ]
    extras = [
        extra for extra in await list_extras(session, tenant.id) if extra.is_active
    ]
    seen: set[UUID] = set()
    categories: list[CategoryChip] = []
    for package in packages:
        if package.category_id in seen:
            continue
        seen.add(package.category_id)
        categories.append(
            CategoryChip(id=package.category_id, name=package.category_name)
        )
    known = {chip.name for chip in categories}
    tags = [tag for tag in tenant.category_tags if tag and tag not in known]
    days = [
        CalendarDay(
            iso=day.isoformat(),
            label=f"{SHORT_DAYS[day.weekday()]} {day.day}",
        )
        for day in upcoming_days(date.today())
    ]
    schedule = [
        slot for slot in await list_slot_reads(session, tenant.id) if slot.is_active
    ]
    return LandingPage(
        slug=tenant.slug,
        tenant_id=tenant.id,
        business_name=tenant.business_name,
        rfc=tenant.rfc,
        address=tenant.address,
        logo_url=tenant.logo_url,
        categories=categories,
        tags=tags,
        photos=await list_photos(session, tenant.id),
        schedule=schedule,
        packages=packages,
        extras=extras,
        zones=await list_zones(session, tenant.id),
        days=days,
        show_prices=tenant.show_prices_public,
        available=bool(tenant.has_active_plan),
        concierge_url=concierge_url(tenant),
        min_guests=tenant.min_guests,
        max_guests=tenant.max_guests,
    )


def public_profile(page: LandingPage) -> PublicProfile:
    show = page.show_prices
    return PublicProfile(
        slug=page.slug,
        business_name=page.business_name,
        logo_url=page.logo_url,
        available=page.available,
        show_prices=show,
        message=None if page.available else UNAVAILABLE,
        categories=[chip.name for chip in page.categories] + page.tags,
        photos=page.photos,
        schedule=page.schedule,
        packages=[_public_package(package, show) for package in page.packages],
        extras=[_public_extra(extra, show) for extra in page.extras],
        zones=[_public_zone(zone, show) for zone in page.zones],
        concierge_url=page.concierge_url,
    )


async def public_slots(
    session: AsyncSession, slug: str, event_date: date
) -> tuple[Tenant, list[PublicSlot]]:
    tenant = await tenant_by_slug(session, slug)
    rows = await open_slots(session, tenant, event_date)
    slots = [
        PublicSlot(
            id=slot.id,
            label=slot_label(slot.start_time, slot.end_time),
            start_time=f"{slot.start_time:%H:%M}",
            end_time=f"{slot.end_time:%H:%M}",
            remaining=remaining,
        )
        for slot, remaining in rows
    ]
    return tenant, slots


async def preview_public_quote(
    session: AsyncSession, slug: str, data: PublicQuoteIn
) -> PricePreview:
    tenant = await tenant_by_slug(session, slug)
    require_bookable(tenant)
    priced = await _price_event(session, tenant, data, discount=Decimal("0"))
    return _preview(tenant, priced)


async def submit_public_quote(
    session: AsyncSession, slug: str, data: PublicQuoteIn
) -> PublicQuoteOut:
    tenant = await tenant_by_slug(session, slug)
    return await submit_quote_for_tenant(
        session, tenant, data, LeadSource.MICRO_LANDING
    )


async def submit_quote_for_tenant(
    session: AsyncSession,
    tenant: Tenant,
    data: PublicQuoteIn,
    source: LeadSource,
) -> PublicQuoteOut:
    require_bookable(tenant)
    priced = await _price_event(session, tenant, data, discount=Decimal("0"))
    name = clean_name(data.full_name)
    phone = require_phone(data.phone)
    whatsapp = require_phone(data.whatsapp_phone)
    venue = clean_text(data.venue_address, limit=500)
    if not venue:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Indica la dirección del evento",
        )
    lead = Lead(
        tenant_id=tenant.id,
        full_name=name,
        phone=phone,
        whatsapp_phone=whatsapp,
        email=clean_email(data.email),
        source=source,
    )
    session.add(lead)
    await session.flush()
    quote = Quote(
        tenant_id=tenant.id,
        lead_id=lead.id,
        package_id=data.package_id,
        delivery_zone_id=data.delivery_zone_id,
        event_date=data.event_date,
        slot_id=data.slot_id,
        venue_address=venue,
        guest_count=data.guest_count,
        waiters_count=priced.waiters,
        selected_options_json=_option_ids(data),
        selected_extras_json={
            "items": list(priced.extras),
            "options": list(priced.options),
            "package_name": priced.package_name,
            "package_price": money_text(priced.package_price),
            "freight": money_text(priced.freight),
            "freight_name": priced.freight_name,
            "waiter_cost": money_text(priced.waiter_cost),
        },
        selected_equipment_json={"lines": list(priced.equipment)},
        subtotal=priced.subtotal,
        discount_amount=priced.discount,
        tax_amount=priced.tax,
        total_amount=priced.total,
        estimated_cogs=priced.cogs,
        status=QuoteStatus.PENDING_REVIEW,
        special_requests=clean_text(data.special_requests) or None,
    )
    session.add(quote)
    await session.flush()
    tracking = notify_new_quote(
        tenant=tenant, lead=lead, token=quote.public_token, event_date=data.event_date
    )
    return _public_out(tenant, quote, priced.package_name, priced.slot_label, tracking)


def notify_new_quote(
    *, tenant: Tenant, lead: Lead, token: UUID, event_date: date
) -> str:
    """WhatsApp the provider and email the lead when SMTP is configured.

    Tenant has a WhatsApp number and no email column, so the provider notice
    is the wa.me link. Mail goes to the address the guest left on the quote.
    """
    tracking = wa_link(
        settings.IBISTRO_CONCIERGE_PHONE or tenant.whatsapp_phone,
        f"Hola, mi folio de cotización es {token}",
    )
    provider = wa_link(
        tenant.whatsapp_phone,
        (
            f"Nueva cotización {token} de {lead.full_name} "
            f"para el {event_date:%d/%m/%Y}."
        ),
    )
    if provider:
        logger.info("provider whatsapp notification %s", provider)
    if settings.emails_enabled and lead.email:
        try:
            send_email(
                email_to=lead.email,
                subject=f"Nueva cotización {token}",
                html_content=render_email_template(
                    template_name="new_quote.html",
                    context={
                        "business_name": tenant.business_name,
                        "lead_name": lead.full_name,
                        "event_date": f"{event_date:%d/%m/%Y}",
                        "token": str(token),
                        "tracking_url": tracking,
                    },
                ),
            )
        except Exception:
            logger.exception("quote email failed")
    return tracking


async def quotes_screen(session: AsyncSession, tenant: Tenant) -> QuotesScreen:
    return QuotesScreen(
        quotes=await list_quotes(session, tenant.id),
        slots=await list_slot_reads(session, tenant.id),
        photos=await list_photos(session, tenant.id),
        zones=await list_zones(session, tenant.id),
        tax_rate=tenant.default_tax_rate,
        slug=tenant.slug,
        business_name=tenant.business_name,
    )


async def list_quotes(session: AsyncSession, tenant_id: UUID) -> list[QuoteDetail]:
    result = await session.exec(select(Quote).where(Quote.tenant_id == tenant_id))
    rows = list(result.all())
    rows.sort(key=lambda row: (row.created_at, str(row.id)), reverse=True)
    details: list[QuoteDetail] = []
    for row in rows:
        details.append(await _detail(session, tenant_id, row))
    return details


async def get_quote(
    session: AsyncSession, tenant_id: UUID, quote_id: UUID
) -> QuoteDetail:
    quote = await _owned_quote(session, tenant_id, quote_id)
    return await _detail(session, tenant_id, quote)


async def adjust_quote(
    session: AsyncSession,
    tenant: Tenant,
    quote_id: UUID,
    data: QuoteAdjustIn,
) -> QuoteDetail:
    quote = await _owned_quote(session, tenant.id, quote_id)
    if quote.status is QuoteStatus.APPROVED or await _reservation_for(
        session, tenant.id, quote.id
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="La cotización ya está aprobada",
        )
    rate = (
        clean_rate(data.tax_rate)
        if data.tax_rate is not None
        else clean_rate(Decimal(str(tenant.default_tax_rate)))
    )
    discount, tax, total = quote_totals(
        quote.subtotal, data.discount_amount, rate, data.apply_tax
    )
    quote.discount_amount = discount
    quote.tax_amount = tax
    quote.total_amount = total
    session.add(quote)
    await session.flush()
    return await _detail(session, tenant.id, quote)


async def quote_pdf(
    session: AsyncSession, tenant: Tenant, quote_id: UUID
) -> tuple[str, bytes]:
    quote = await _owned_quote(session, tenant.id, quote_id)
    detail = await _detail(session, tenant.id, quote)
    payload = quote.selected_extras_json
    equipment = _dict_lines(quote.selected_equipment_json.get("lines"))
    document = QuoteDocument(
        business_name=tenant.business_name,
        rfc=tenant.rfc,
        address=tenant.address,
        client_name=detail.lead_name,
        phone=detail.phone,
        event_date=detail.event_date.isoformat(),
        slot_label=detail.slot_label,
        venue=detail.venue_address,
        guests=str(detail.guest_count),
        waiters=str(detail.waiters_count),
        package_name=detail.package_name,
        options=tuple(
            (line["group"], line["recipe"])
            for line in _dict_lines(payload.get("options"))
        ),
        extras=tuple(
            (line["name"], line.get("amount", "0.00"))
            for line in _dict_lines(payload.get("items"))
        ),
        equipment=tuple(
            (f"{line['name']} x{line['units']}", line.get("rental", "0.00"))
            for line in equipment
        ),
        package_price=str(payload.get("package_price", money_text(quote.subtotal))),
        waiter_cost=str(payload.get("waiter_cost", "0.00")),
        freight_name=str(payload.get("freight_name") or "Flete"),
        freight=str(payload.get("freight", "0.00")),
        subtotal=money_text(quote.subtotal),
        discount=money_text(quote.discount_amount),
        tax=money_text(quote.tax_amount),
        total=money_text(quote.total_amount),
        special_requests=quote.special_requests or "",
        token=str(quote.public_token),
        status_label=detail.status_label,
    )
    return str(quote.public_token), render_quote_pdf(document)


async def convert_quote(
    session: AsyncSession, tenant: Tenant, quote_id: UUID
) -> QuoteDetail:
    quote = await _owned_quote(session, tenant.id, quote_id)
    if await _reservation_for(session, tenant.id, quote.id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Esta cotización ya es una reservación",
        )
    if quote.status is QuoteStatus.REJECTED:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="La cotización está rechazada",
        )
    lead = await session.get(Lead, quote.lead_id)
    if lead is None or lead.tenant_id != tenant.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No se encontró el contacto",
        )
    await assert_slot_open(session, tenant, quote.event_date, quote.slot_id)
    equipment = _dict_lines(quote.selected_equipment_json.get("lines"))
    await _assert_equipment(session, tenant.id, quote.event_date, equipment, quote.id)
    quoted = await quote_for_package(
        session,
        tenant.id,
        quote.package_id,
        QuoteIn(
            guest_count=quote.guest_count,
            selected_options=_stored_options(quote.selected_options_json),
            extras=[
                QuoteExtraIn(
                    extra_id=UUID(line["extra_id"]),
                    quantity=float(line["quantity"]),
                )
                for line in _dict_lines(quote.selected_extras_json.get("items"))
            ],
        ),
    )
    reservation = Reservation(
        tenant_id=tenant.id,
        quote_id=quote.id,
        customer_name=lead.full_name,
        customer_phone=lead.whatsapp_phone or lead.phone,
        venue_address=quote.venue_address,
        event_date=quote.event_date,
        slot_id=quote.slot_id,
        guest_count=quote.guest_count,
        total_amount=quote.total_amount,
        paid_amount=Decimal("0.00"),
        payment_status=PaymentStatus.UNPAID,
        operation_status=OperationStatus.CONFIRMED,
        special_requests=quote.special_requests,
    )
    session.add(reservation)
    await session.flush()
    needs = [
        IngredientNeed(
            ingredient_id=line.ingredient_id,
            net_qty=line.net_qty,
            gross_qty=line.gross_qty,
            cost=line.cost,
        )
        for line in quoted.explosion
        if line.gross_qty > 0
    ]
    try:
        if needs:
            await commit_recipe_explosion(
                session,
                tenant_id=tenant.id,
                lines=needs,
                reference_id=reservation.id,
            )
    except HTTPException:
        await session.delete(reservation)
        raise
    quote.status = QuoteStatus.APPROVED
    session.add(quote)
    await session.flush()
    return await _detail(session, tenant.id, quote)


async def _price_event(
    session: AsyncSession,
    tenant: Tenant,
    data: PublicQuoteIn,
    discount: Decimal,
) -> PricedEvent:
    package = await _active_package(session, tenant.id, data.package_id)
    _check_guests(tenant, package, data.guest_count)
    slot = await assert_slot_open(session, tenant, data.event_date, data.slot_id)
    zone = await _zone(session, tenant.id, data.delivery_zone_id)
    quoted = await quote_for_package(
        session,
        tenant.id,
        package.id,
        QuoteIn(
            guest_count=data.guest_count,
            selected_options=data.selected_options,
            extras=data.extras,
        ),
    )
    extras = _extra_lines(await list_extras(session, tenant.id), data)
    extra_total = sum(
        (Decimal(line["amount"]) for line in extras),
        Decimal("0"),
    )
    equipment = await _equipment_lines(session, tenant.id, package.id, data.guest_count)
    await _assert_equipment(
        session, tenant.id, data.event_date, equipment, ignore_quote_id=None
    )
    equipment_total = sum(
        (Decimal(line["rental"]) for line in equipment),
        Decimal("0"),
    )
    waiters = waiter_count(data.guest_count, tenant.waiter_ratio)
    waiter_cost = as_money(Decimal(waiters) * tenant.waiter_cost_per_event)
    freight = zone.freight_cost if zone is not None else Decimal("0.00")
    subtotal = as_money(quoted.price + waiter_cost + freight + equipment_total)
    rate = clean_rate(Decimal(str(tenant.default_tax_rate)))
    discount, tax, total = quote_totals(subtotal, discount, rate, rate > 0)
    needs = tuple(
        IngredientNeed(
            ingredient_id=line.ingredient_id,
            net_qty=line.net_qty,
            gross_qty=line.gross_qty,
            cost=line.cost,
        )
        for line in quoted.explosion
    )
    return PricedEvent(
        package_name=package.name,
        package_price=as_money(quoted.price - extra_total),
        extras=tuple(extras),
        options=tuple(_option_names(package, data)),
        equipment=tuple(equipment),
        freight=as_money(freight),
        freight_name=zone.zone_name if zone is not None else "",
        waiter_cost=waiter_cost,
        waiters=waiters,
        subtotal=subtotal,
        discount=discount,
        tax=tax,
        total=total,
        cogs=quoted.cogs,
        explosion=needs,
        slot_label=slot_label(slot.start_time, slot.end_time),
    )


async def _active_package(
    session: AsyncSession, tenant_id: UUID, package_id: UUID
) -> PackageRead:
    for package in await list_packages(session, tenant_id):
        if package.id == package_id:
            if not package.is_active:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail="El paquete no está disponible",
                )
            return package
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="No se encontró el paquete",
    )


def _check_guests(tenant: Tenant, package: PackageRead, guests: int) -> None:
    minimum = max(tenant.min_guests, package.min_guests)
    if guests < minimum:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"El mínimo de invitados es {minimum}",
        )
    if guests > tenant.max_guests:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"El máximo de invitados es {tenant.max_guests}",
        )


async def _zone(
    session: AsyncSession, tenant_id: UUID, zone_id: UUID | None
) -> DeliveryZone | None:
    if zone_id is None:
        return None
    zone = await owned(
        session, DeliveryZone, zone_id, tenant_id, "No se encontró la zona"
    )
    return zone


def _extra_lines(extras: list[ExtraRead], data: PublicQuoteIn) -> list[dict[str, str]]:
    catalog = {extra.id: extra for extra in extras}
    lines: list[dict[str, str]] = []
    for requested in data.extras:
        extra = catalog.get(requested.extra_id)
        if extra is None:
            continue
        if extra.pricing_type is PricingType.PER_GUEST:
            amount = as_money(extra.unit_price * Decimal(data.guest_count))
        else:
            amount = as_money(extra.unit_price * Decimal(str(requested.quantity)))
        lines.append(
            {
                "extra_id": str(extra.id),
                "name": extra.name,
                "quantity": str(requested.quantity),
                "amount": money_text(amount),
            }
        )
    return lines


def _option_names(package: PackageRead, data: PublicQuoteIn) -> list[dict[str, str]]:
    lines: list[dict[str, str]] = []
    for group in package.groups:
        chosen = set(data.selected_options.get(group.id, []))
        for option in group.options:
            if group.is_fixed or option.recipe_id in chosen:
                lines.append({"group": group.group_name, "recipe": option.recipe_name})
    return lines


def _option_ids(data: PublicQuoteIn) -> dict[str, list[str]]:
    return {
        str(group_id): [str(recipe_id) for recipe_id in recipes]
        for group_id, recipes in data.selected_options.items()
    }


async def _equipment_lines(
    session: AsyncSession, tenant_id: UUID, package_id: UUID, guests: int
) -> list[dict[str, str]]:
    result = await session.exec(
        select(PackageEquipmentRule).where(PackageEquipmentRule.tenant_id == tenant_id)
    )
    rules = [row for row in result.all() if row.package_id == package_id]
    assets = await _assets(session, tenant_id)
    lines: list[dict[str, str]] = []
    for rule in rules:
        asset = assets.get(rule.asset_id)
        if asset is None:
            continue
        try:
            units = equipment_units(guests, rule.guests_per_unit)
        except CostError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=str(exc),
            )
        rental = as_money(asset.rental_price_per_unit * Decimal(units))
        lines.append(
            {
                "asset_id": str(asset.id),
                "name": asset.name,
                "units": str(units),
                "rental": money_text(rental),
            }
        )
    return lines


async def _assets(session: AsyncSession, tenant_id: UUID) -> dict[UUID, EquipmentAsset]:
    result = await session.exec(
        select(EquipmentAsset).where(EquipmentAsset.tenant_id == tenant_id)
    )
    return {row.id: row for row in result.all()}


async def _assert_equipment(
    session: AsyncSession,
    tenant_id: UUID,
    event_date: date,
    lines: list[dict[str, str]] | tuple[dict[str, str], ...],
    ignore_quote_id: UUID | None,
) -> None:
    if not lines:
        return
    assets = await _assets(session, tenant_id)
    booked = await _booked_units(session, tenant_id, event_date, ignore_quote_id)
    for line in lines:
        units = int(line["units"])
        if units <= 0:
            continue
        asset_id = UUID(line["asset_id"])
        asset = assets.get(asset_id)
        if asset is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No se encontró el equipo",
            )
        if booked.get(asset_id, 0) + units > asset.total_stock:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="No hay equipo disponible para esa fecha",
            )


async def _booked_units(
    session: AsyncSession,
    tenant_id: UUID,
    event_date: date,
    ignore_quote_id: UUID | None,
) -> dict[UUID, int]:
    totals: dict[UUID, int] = {}
    for reservation in await open_reservations(session, tenant_id, event_date):
        if reservation.quote_id is None or reservation.quote_id == ignore_quote_id:
            continue
        quote = await session.get(Quote, reservation.quote_id)
        if quote is None or quote.tenant_id != tenant_id:
            continue
        for line in _dict_lines(quote.selected_equipment_json.get("lines")):
            asset_id = UUID(line["asset_id"])
            totals[asset_id] = totals.get(asset_id, 0) + int(line["units"])
    return totals


def _dict_lines(value: object) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []
    lines: list[dict[str, str]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        lines.append({str(key): str(item[key]) for key in item})
    return lines


def _stored_options(raw: Mapping[str, Any]) -> dict[UUID, list[UUID]]:
    selected: dict[UUID, list[UUID]] = {}
    for key, value in raw.items():
        try:
            group_id = UUID(str(key))
        except ValueError:
            continue
        if not isinstance(value, list):
            continue
        selected[group_id] = [UUID(str(item)) for item in value]
    return selected


def _preview(tenant: Tenant, priced: PricedEvent) -> PricePreview:
    show = tenant.show_prices_public
    return PricePreview(
        show_prices=show,
        message=HIDDEN_PRICE if not show else "Desglose estimado",
        package_name=priced.package_name,
        waiters_count=priced.waiters,
        subtotal=priced.subtotal if show else None,
        discount_amount=priced.discount if show else None,
        tax_amount=priced.tax if show else None,
        total_amount=priced.total if show else None,
    )


def _public_out(
    tenant: Tenant, quote: Quote, package_name: str, slot: str, tracking: str
) -> PublicQuoteOut:
    show = tenant.show_prices_public
    return PublicQuoteOut(
        id=quote.id,
        public_token=quote.public_token,
        status=quote.status,
        show_prices=show,
        message=HIDDEN_PRICE if not show else "Cotización registrada",
        package_name=package_name,
        event_date=quote.event_date,
        slot_label=slot,
        guest_count=quote.guest_count,
        subtotal=quote.subtotal if show else None,
        discount_amount=quote.discount_amount if show else None,
        tax_amount=quote.tax_amount if show else None,
        total_amount=quote.total_amount if show else None,
        tracking_url=tracking,
    )


async def _detail(session: AsyncSession, tenant_id: UUID, quote: Quote) -> QuoteDetail:
    lead = await session.get(Lead, quote.lead_id)
    package_name = str(quote.selected_extras_json.get("package_name") or "")
    if not package_name:
        for package in await list_packages(session, tenant_id):
            if package.id == quote.package_id:
                package_name = package.name
                break
    if not package_name:
        package_name = "Paquete"
    slot_text = ""
    found = await session.get(ServiceScheduleSlot, quote.slot_id)
    if found is not None:
        slot_text = slot_label(found.start_time, found.end_time)
    reservation = await _reservation_for(session, tenant_id, quote.id)
    taxable = quote.subtotal - quote.discount_amount
    return QuoteDetail(
        id=quote.id,
        public_token=quote.public_token,
        status=quote.status,
        status_label=STATUS_LABELS.get(quote.status, quote.status.value),
        lead_name=lead.full_name if lead is not None else "Cliente",
        phone=lead.phone if lead is not None else "",
        whatsapp_phone=lead.whatsapp_phone if lead is not None else "",
        email=lead.email if lead is not None else None,
        package_name=package_name,
        event_date=quote.event_date,
        slot_label=slot_text,
        venue_address=quote.venue_address,
        guest_count=quote.guest_count,
        waiters_count=quote.waiters_count,
        subtotal=quote.subtotal,
        discount_amount=quote.discount_amount,
        tax_amount=quote.tax_amount,
        total_amount=quote.total_amount,
        estimated_cogs=quote.estimated_cogs,
        special_requests=quote.special_requests,
        reservation_id=reservation.id if reservation is not None else None,
        apply_tax=quote.tax_amount > 0,
        tax_rate=_implied_rate(quote, taxable),
    )


def _implied_rate(quote: Quote, taxable: Decimal) -> Decimal:
    if quote.tax_amount > 0 and taxable > 0:
        return (quote.tax_amount / taxable).quantize(Decimal("0.0001"))
    return Decimal("0.00")


async def _reservation_for(
    session: AsyncSession, tenant_id: UUID, quote_id: UUID
) -> Reservation | None:
    result = await session.exec(
        select(Reservation).where(Reservation.tenant_id == tenant_id)
    )
    for row in result.all():
        if row.quote_id == quote_id:
            return row
    return None


async def _owned_quote(session: AsyncSession, tenant_id: UUID, quote_id: UUID) -> Quote:
    return await owned(
        session, Quote, quote_id, tenant_id, "No se encontró la cotización"
    )


def _public_package(package: PackageRead, show: bool) -> PublicPackage:
    return PublicPackage(
        id=package.id,
        category_id=package.category_id,
        category_name=package.category_name,
        name=package.name,
        description=package.description,
        min_guests=package.min_guests,
        base_price_per_guest=package.base_price_per_guest if show else None,
        groups=[
            PublicGroup(
                id=group.id,
                group_name=group.group_name,
                min_choices=group.min_choices,
                max_choices=group.max_choices,
                is_fixed=group.is_fixed,
                options=[
                    PublicOption(
                        recipe_id=option.recipe_id,
                        recipe_name=option.recipe_name,
                        extra_price_per_guest=option.extra_price_per_guest
                        if show
                        else None,
                    )
                    for option in group.options
                ],
            )
            for group in package.groups
        ],
    )


def _public_extra(extra: ExtraRead, show: bool) -> PublicExtra:
    return PublicExtra(
        id=extra.id,
        name=extra.name,
        pricing_type=extra.pricing_type,
        unit_price=extra.unit_price if show else None,
    )


def _public_zone(zone: ZoneRead, show: bool) -> PublicZone:
    return PublicZone(
        id=zone.id,
        zone_name=zone.zone_name,
        freight_cost=zone.freight_cost if show else None,
    )
