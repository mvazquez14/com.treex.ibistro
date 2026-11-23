"""JSON consumed by Orion, the WhatsApp CRM."""

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.api.deps import OrionKey, SessionDep, require_orion_key
from app.schemas.concierge import (
    ConciergeAvailability,
    ConciergeCategory,
    ConciergeMenu,
    ConciergeProvider,
    ConciergeQuoteIn,
    ConciergeQuoteOut,
)
from app.services import concierge

router = APIRouter(
    prefix="/concierge",
    tags=["concierge"],
    dependencies=[Depends(require_orion_key)],
)


@router.get("/categories", response_model=list[ConciergeCategory])
async def categories(session: SessionDep, _key: OrionKey) -> list[ConciergeCategory]:
    return await concierge.list_categories(session)


@router.get("/providers/search", response_model=list[ConciergeProvider])
async def search_providers(
    session: SessionDep,
    _key: OrionKey,
    category_slug: str = Query(min_length=1),
    guest_count: int = Query(ge=1),
    event_date: date = Query(),
) -> list[ConciergeProvider]:
    return await concierge.search_providers(
        session,
        category_slug=category_slug,
        guest_count=guest_count,
        event_date=event_date,
    )


@router.get(
    "/providers/{provider_id}/availability",
    response_model=ConciergeAvailability,
)
async def provider_availability(
    session: SessionDep, _key: OrionKey, provider_id: UUID
) -> ConciergeAvailability:
    return await concierge.provider_availability(session, provider_id)


@router.get(
    "/providers/{provider_id}/menu",
    response_model=ConciergeMenu,
    response_model_exclude_none=True,
)
async def provider_menu(
    session: SessionDep, _key: OrionKey, provider_id: UUID
) -> ConciergeMenu:
    return await concierge.provider_menu(session, provider_id)


@router.post("/quotes", response_model=ConciergeQuoteOut)
async def create_quote(
    session: SessionDep, _key: OrionKey, data: ConciergeQuoteIn
) -> ConciergeQuoteOut:
    created = await concierge.create_quote(session, data)
    await session.commit()
    return created
