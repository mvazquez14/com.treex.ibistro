"""Authenticated JSON for quotes."""

from uuid import UUID

from fastapi import APIRouter
from starlette.responses import Response

from app.api.deps import CurrentActiveTenant, SessionDep
from app.schemas.quotes import QuoteAdjustIn, QuoteDetail
from app.services import quoting

router = APIRouter(prefix="/quotes", tags=["quotes"])


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


@router.post("/{quote_id}/convert", response_model=QuoteDetail)
async def convert_quote(
    session: SessionDep, tenant: CurrentActiveTenant, quote_id: UUID
) -> QuoteDetail:
    updated = await quoting.convert_quote(session, tenant, quote_id)
    await session.commit()
    return updated
