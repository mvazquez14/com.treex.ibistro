from uuid import UUID

from fastapi import APIRouter, status

from app.api.deps import CurrentActiveTenant, SessionDep
from app.schemas.catalog import (
    AssetIn,
    AssetRead,
    AssetUpdate,
    RuleIn,
    RuleRead,
    RuleUpdate,
)
from app.services import equipment_catalog as catalog

router = APIRouter(prefix="/equipment", tags=["equipment"])


@router.get("/preview")
async def preview_units(
    _tenant: CurrentActiveTenant, guests: int, guests_per_unit: int
) -> dict[str, int]:
    return {"units": catalog.preview_units(guests, guests_per_unit)}


@router.get("/assets", response_model=list[AssetRead])
async def list_assets(
    session: SessionDep, tenant: CurrentActiveTenant
) -> list[AssetRead]:
    return await catalog.list_assets(session, tenant.id)


@router.post("/assets", response_model=AssetRead, status_code=status.HTTP_201_CREATED)
async def create_asset(
    session: SessionDep, tenant: CurrentActiveTenant, data: AssetIn
) -> AssetRead:
    row = await catalog.create_asset(session, tenant.id, data)
    await session.commit()
    return row


@router.patch("/assets/{asset_id}", response_model=AssetRead)
async def update_asset(
    session: SessionDep,
    tenant: CurrentActiveTenant,
    asset_id: UUID,
    data: AssetUpdate,
) -> AssetRead:
    row = await catalog.update_asset(session, tenant.id, asset_id, data)
    await session.commit()
    return row


@router.delete("/assets/{asset_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_asset(
    session: SessionDep, tenant: CurrentActiveTenant, asset_id: UUID
) -> None:
    await catalog.delete_asset(session, tenant.id, asset_id)
    await session.commit()


@router.get("/rules", response_model=list[RuleRead])
async def list_rules(
    session: SessionDep, tenant: CurrentActiveTenant, guests: int = 25
) -> list[RuleRead]:
    return await catalog.list_rules(session, tenant.id, guests=guests)


@router.post("/rules", response_model=RuleRead, status_code=status.HTTP_201_CREATED)
async def create_rule(
    session: SessionDep,
    tenant: CurrentActiveTenant,
    data: RuleIn,
    guests: int = 25,
) -> RuleRead:
    row = await catalog.create_rule(session, tenant.id, data, guests=guests)
    await session.commit()
    return row


@router.patch("/rules/{rule_id}", response_model=RuleRead)
async def update_rule(
    session: SessionDep,
    tenant: CurrentActiveTenant,
    rule_id: UUID,
    data: RuleUpdate,
    guests: int = 25,
) -> RuleRead:
    row = await catalog.update_rule(session, tenant.id, rule_id, data, guests=guests)
    await session.commit()
    return row


@router.delete("/rules/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_rule(
    session: SessionDep, tenant: CurrentActiveTenant, rule_id: UUID
) -> None:
    await catalog.delete_rule(session, tenant.id, rule_id)
    await session.commit()
