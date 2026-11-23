"""JSON for the provider reports."""

from fastapi import APIRouter

from app.api.deps import CurrentActiveTenant, SessionDep
from app.schemas.operations import ProviderReports
from app.services import reports

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("", response_model=ProviderReports)
async def read_reports(
    session: SessionDep, tenant: CurrentActiveTenant
) -> ProviderReports:
    return await reports.provider_reports(session, tenant)
