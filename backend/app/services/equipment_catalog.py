"""Equipment assets and the per-guest rules of a package. Rules preview units; they do not reserve dates."""

from uuid import UUID

from fastapi import HTTPException, status
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.enums import EquipmentCategory
from app.models.equipment import EquipmentAsset, PackageEquipmentRule
from app.models.menu import CateringPackage
from app.schemas.catalog import (
    AssetIn,
    AssetRead,
    AssetUpdate,
    EquipmentScreen,
    PackageChoice,
    RuleIn,
    RuleRead,
    RuleUpdate,
)
from app.services.catalog_common import (
    as_enum,
    clean_money,
    clean_name,
    conflict,
    owned,
)
from app.services.cost_engine import CostError, equipment_units


async def equipment_snapshot(
    session: AsyncSession, tenant_id: UUID, *, guests: int
) -> EquipmentScreen:
    guest_count = _guests(guests)
    return EquipmentScreen(
        assets=await list_assets(session, tenant_id),
        rules=await list_rules(session, tenant_id, guests=guest_count),
        packages=await _package_choices(session, tenant_id),
        guests=guest_count,
    )


async def list_assets(session: AsyncSession, tenant_id: UUID) -> list[AssetRead]:
    rows = await _assets(session, tenant_id)
    return [_asset_read(row) for row in rows]


async def create_asset(
    session: AsyncSession, tenant_id: UUID, data: AssetIn
) -> AssetRead:
    row = EquipmentAsset(
        tenant_id=tenant_id,
        name=clean_name(data.name),
        category=data.category,
        total_stock=_total_stock(data.total_stock),
        rental_price_per_unit=clean_money(data.rental_price_per_unit, "La renta"),
        replacement_cost=clean_money(data.replacement_cost, "El costo de reposición"),
    )
    session.add(row)
    await session.flush()
    return _asset_read(row)


async def update_asset(
    session: AsyncSession, tenant_id: UUID, asset_id: UUID, data: AssetUpdate
) -> AssetRead:
    row = await owned(
        session, EquipmentAsset, asset_id, tenant_id, "No se encontró el equipo"
    )
    fields = data.model_fields_set
    if "name" in fields and data.name is not None:
        row.name = clean_name(data.name)
    if "category" in fields and data.category is not None:
        row.category = data.category
    if "total_stock" in fields and data.total_stock is not None:
        row.total_stock = _total_stock(data.total_stock)
    if "rental_price_per_unit" in fields and data.rental_price_per_unit is not None:
        row.rental_price_per_unit = clean_money(data.rental_price_per_unit, "La renta")
    if "replacement_cost" in fields and data.replacement_cost is not None:
        row.replacement_cost = clean_money(
            data.replacement_cost, "El costo de reposición"
        )
    session.add(row)
    await session.flush()
    return _asset_read(row)


async def delete_asset(session: AsyncSession, tenant_id: UUID, asset_id: UUID) -> None:
    row = await owned(
        session, EquipmentAsset, asset_id, tenant_id, "No se encontró el equipo"
    )
    result = await session.exec(
        select(PackageEquipmentRule).where(
            PackageEquipmentRule.tenant_id == tenant_id,
            PackageEquipmentRule.asset_id == asset_id,
        )
    )
    if list(result.all()):
        raise conflict("No se puede eliminar el equipo porque todavía tiene reglas")
    await session.delete(row)


async def list_rules(
    session: AsyncSession, tenant_id: UUID, *, guests: int
) -> list[RuleRead]:
    guest_count = _guests(guests)
    result = await session.exec(
        select(PackageEquipmentRule).where(PackageEquipmentRule.tenant_id == tenant_id)
    )
    packages = {row.id: row.name for row in await _packages(session, tenant_id)}
    assets = {row.id: row.name for row in await _assets(session, tenant_id)}
    reads = [_rule_read(row, packages, assets, guest_count) for row in result.all()]
    reads.sort(key=lambda row: (row.package_name.lower(), row.asset_name.lower()))
    return reads


async def create_rule(
    session: AsyncSession, tenant_id: UUID, data: RuleIn, *, guests: int
) -> RuleRead:
    package = await owned(
        session,
        CateringPackage,
        data.package_id,
        tenant_id,
        "No se encontró el paquete",
    )
    asset = await owned(
        session, EquipmentAsset, data.asset_id, tenant_id, "No se encontró el equipo"
    )
    _guests_per_unit(data.guests_per_unit)
    existing = await session.exec(
        select(PackageEquipmentRule).where(
            PackageEquipmentRule.tenant_id == tenant_id,
            PackageEquipmentRule.package_id == data.package_id,
            PackageEquipmentRule.asset_id == data.asset_id,
        )
    )
    if existing.first() is not None:
        raise conflict("Ese equipo ya tiene una regla en el paquete")
    row = PackageEquipmentRule(
        tenant_id=tenant_id,
        package_id=data.package_id,
        asset_id=data.asset_id,
        guests_per_unit=data.guests_per_unit,
    )
    session.add(row)
    await session.flush()
    return _rule_read(
        row,
        {package.id: package.name},
        {asset.id: asset.name},
        _guests(guests),
    )


async def update_rule(
    session: AsyncSession,
    tenant_id: UUID,
    rule_id: UUID,
    data: RuleUpdate,
    *,
    guests: int,
) -> RuleRead:
    row = await owned(
        session, PackageEquipmentRule, rule_id, tenant_id, "No se encontró la regla"
    )
    row.guests_per_unit = _guests_per_unit(data.guests_per_unit)
    session.add(row)
    await session.flush()
    packages = {item.id: item.name for item in await _packages(session, tenant_id)}
    assets = {item.id: item.name for item in await _assets(session, tenant_id)}
    return _rule_read(row, packages, assets, _guests(guests))


async def delete_rule(session: AsyncSession, tenant_id: UUID, rule_id: UUID) -> None:
    row = await owned(
        session, PackageEquipmentRule, rule_id, tenant_id, "No se encontró la regla"
    )
    await session.delete(row)


def preview_units(guests: int, guests_per_unit: int) -> int:
    try:
        return equipment_units(guests, guests_per_unit)
    except CostError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        )


def parse_category(value: str) -> EquipmentCategory:
    return as_enum(EquipmentCategory, value, "La categoría de equipo no es válida")


def _asset_read(row: EquipmentAsset) -> AssetRead:
    return AssetRead(
        id=row.id,
        name=row.name,
        category=row.category,
        total_stock=row.total_stock,
        rental_price_per_unit=row.rental_price_per_unit,
        replacement_cost=row.replacement_cost,
    )


def _rule_read(
    row: PackageEquipmentRule,
    packages: dict[UUID, str],
    assets: dict[UUID, str],
    guests: int,
) -> RuleRead:
    return RuleRead(
        id=row.id,
        package_id=row.package_id,
        package_name=packages.get(row.package_id, "Paquete"),
        asset_id=row.asset_id,
        asset_name=assets.get(row.asset_id, "Equipo"),
        guests_per_unit=row.guests_per_unit,
        units_for_guests=equipment_units(guests, row.guests_per_unit),
    )


def _guests(value: int) -> int:
    if value < 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="El número de invitados no puede ser negativo",
        )
    return value


def _guests_per_unit(value: int) -> int:
    if value < 1:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Los invitados por unidad deben ser al menos 1",
        )
    return value


def _total_stock(value: int) -> int:
    if value < 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="La existencia de equipo no puede ser negativa",
        )
    return value


async def _assets(session: AsyncSession, tenant_id: UUID) -> list[EquipmentAsset]:
    result = await session.exec(
        select(EquipmentAsset).where(EquipmentAsset.tenant_id == tenant_id)
    )
    rows = list(result.all())
    rows.sort(key=lambda row: row.name.lower())
    return rows


async def _packages(session: AsyncSession, tenant_id: UUID) -> list[CateringPackage]:
    result = await session.exec(
        select(CateringPackage).where(CateringPackage.tenant_id == tenant_id)
    )
    rows = list(result.all())
    rows.sort(key=lambda row: row.name.lower())
    return rows


async def _package_choices(
    session: AsyncSession, tenant_id: UUID
) -> list[PackageChoice]:
    return [
        PackageChoice(id=row.id, name=row.name)
        for row in await _packages(session, tenant_id)
    ]
