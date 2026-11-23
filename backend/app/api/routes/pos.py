"""JSON for counter sales."""

from fastapi import APIRouter

from app.api.deps import CurrentActiveTenant, SessionDep
from app.schemas.operations import PosOrderRead, PosSaleIn, PosScreen
from app.services import pos

router = APIRouter(prefix="/pos", tags=["pos"])


@router.get("", response_model=PosScreen)
async def pos_screen(session: SessionDep, tenant: CurrentActiveTenant) -> PosScreen:
    return await pos.pos_screen(session, tenant)


@router.post("/orders", response_model=PosOrderRead)
async def create_order(
    session: SessionDep, tenant: CurrentActiveTenant, data: PosSaleIn
) -> PosOrderRead:
    order = await pos.checkout(session, tenant, data)
    await session.commit()
    return order
