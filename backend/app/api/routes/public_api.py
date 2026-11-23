"""JSON API for the public micro-landing. HTMX receives the slot partial."""

from datetime import date

from fastapi import APIRouter, HTTPException, Query, Request, status
from fastapi.encoders import jsonable_encoder
from starlette.responses import JSONResponse, Response

from app.api.deps import SessionDep
from app.schemas.quotes import PublicProfile, PublicQuoteIn, PublicQuoteOut
from app.services import quoting
from app.templating import templates

router = APIRouter(prefix="/public", tags=["public"])


def _event_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="La fecha no es válida",
        )


@router.get("/{slug}", response_model=PublicProfile, response_model_exclude_none=True)
async def public_profile(session: SessionDep, slug: str) -> PublicProfile:
    page = await quoting.landing_page(session, slug)
    return quoting.public_profile(page)


@router.get("/{slug}/slots")
async def public_slots(
    request: Request,
    session: SessionDep,
    slug: str,
    event_date: str = Query(alias="date"),
) -> Response:
    day = _event_date(event_date)
    tenant, slots = await quoting.public_slots(session, slug, day)
    if request.headers.get("hx-request"):
        message = quoting.UNAVAILABLE if not tenant.has_active_plan else None
        return templates.TemplateResponse(
            request,
            "public/slots.html",
            {"slots": slots, "event_date": day.isoformat(), "message": message},
        )
    return JSONResponse(jsonable_encoder(slots))


@router.post(
    "/{slug}/quotes",
    response_model=PublicQuoteOut,
    response_model_exclude_none=True,
    status_code=status.HTTP_201_CREATED,
)
async def public_quote(
    session: SessionDep, slug: str, data: PublicQuoteIn
) -> PublicQuoteOut:
    created = await quoting.submit_public_quote(session, slug, data)
    await session.commit()
    return created
