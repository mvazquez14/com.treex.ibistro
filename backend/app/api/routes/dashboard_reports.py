"""HTMX provider reports."""

from fastapi import APIRouter, Request
from starlette.responses import Response

from app.api.deps import CurrentActiveTenant, SessionDep
from app.services import reports
from app.templating import render

router = APIRouter(prefix="/reports", tags=["dashboard"])


@router.get("")
async def reports_page(
    request: Request, session: SessionDep, tenant: CurrentActiveTenant
) -> Response:
    screen = await reports.provider_reports(session, tenant)
    return render(
        request,
        "dashboard/reports.html",
        "dashboard/reports_panel.html",
        {"section": "reports", "screen": screen},
    )
