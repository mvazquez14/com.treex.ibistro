"""Authenticated JSON for quotes."""

from uuid import UUID

from fastapi import APIRouter, Body, status
from starlette.responses import Response

from app.api.deps import CurrentActiveTenant, SessionDep
from app.models.enums import LeadSource
from app.schemas.quotes import PublicQuoteIn, QuoteAdjustIn, QuoteDetail, ScheduleChoice
from app.services import quoting

router = APIRouter(prefix="/quotes", tags=["quotes"])


@router.post("", response_model=QuoteDetail, status_code=status.HTTP_201_CREATED)
async def create_quote(
    session: SessionDep, tenant: CurrentActiveTenant, data: PublicQuoteIn
) -> QuoteDetail:
    created = await quoting.submit_quote_for_tenant(
        session, tenant, data, LeadSource.MANUAL_DASHBOARD
    )
    detail = await quoting.get_quote(session, tenant.id, created.id)
    await session.commit()
    return detail


@router.get("", response_model=list[QuoteDetail])
async def list_quotes(
    session: SessionDep, tenant: CurrentActiveTenant
) -> list[QuoteDetail]:
    return await quoting.list_quotes(session, tenant.id)


@router.get("/{quote_id}", response_model=QuoteDetail)
async def get_quote(
    session: SessionDep, tenant: CurrentActiveTenant, quote_id: UUID
) -> QuoteDetail:
    return await quoting.get_quote(session, tenant.id, quote_id)


@router.patch("/{quote_id}", response_model=QuoteDetail)
async def adjust_quote(
    session: SessionDep,
    tenant: CurrentActiveTenant,
    quote_id: UUID,
    data: QuoteAdjustIn,
) -> QuoteDetail:
    updated = await quoting.adjust_quote(session, tenant, quote_id, data)
    await session.commit()
    return updated


@router.patch("/{quote_id}/schedule", response_model=QuoteDetail)
async def reschedule_quote(
    session: SessionDep,
    tenant: CurrentActiveTenant,
    quote_id: UUID,
    data: ScheduleChoice,
) -> QuoteDetail:
    updated = await quoting.reschedule_quote(session, tenant, quote_id, data)
    await session.commit()
    return updated


@router.get("/{quote_id}/pdf")
async def quote_pdf(
    session: SessionDep, tenant: CurrentActiveTenant, quote_id: UUID
) -> Response:
    token, payload = await quoting.quote_pdf(session, tenant, quote_id)
    return Response(
        content=payload,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="cotizacion-{token}.pdf"'
        },
    )


@router.post("/{quote_id}/approve", response_model=QuoteDetail)
async def approve_quote(
    session: SessionDep, tenant: CurrentActiveTenant, quote_id: UUID
) -> QuoteDetail:
    updated = await quoting.approve_quote(session, tenant, quote_id)
    await session.commit()
    return updated


@router.post("/{quote_id}/convert", response_model=QuoteDetail)
async def convert_quote(
    session: SessionDep,
    tenant: CurrentActiveTenant,
    quote_id: UUID,
    data: ScheduleChoice | None = Body(default=None),
) -> QuoteDetail:
    updated = await quoting.convert_quote(session, tenant, quote_id, data)
    await session.commit()
    return updated
