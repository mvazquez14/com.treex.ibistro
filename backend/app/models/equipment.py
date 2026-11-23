import uuid
from decimal import Decimal

from sqlalchemy import Column, Integer
from sqlmodel import Field, SQLModel

from app.models.columns import enum_column, fk, money_column, uuid_pk
from app.models.enums import EquipmentCategory


class EquipmentAsset(SQLModel, table=True):
    __tablename__ = "equipment_asset"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, sa_column=uuid_pk())
    tenant_id: uuid.UUID = Field(sa_column=fk("tenant.id"))
    name: str = Field(max_length=255)
    category: EquipmentCategory = Field(
        sa_column=enum_column(EquipmentCategory, "equipment_category")
    )
    total_stock: int = Field(sa_column=Column(Integer, nullable=False))
    rental_price_per_unit: Decimal = Field(
        default=Decimal("0.00"),
        sa_column=money_column(),
    )
    replacement_cost: Decimal = Field(sa_column=money_column())


class PackageEquipmentRule(SQLModel, table=True):
    __tablename__ = "package_equipment_rule"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, sa_column=uuid_pk())
    tenant_id: uuid.UUID = Field(sa_column=fk("tenant.id"))
    package_id: uuid.UUID = Field(sa_column=fk("catering_package.id"))
    asset_id: uuid.UUID = Field(sa_column=fk("equipment_asset.id"))
    guests_per_unit: int = Field(sa_column=Column(Integer, nullable=False))
