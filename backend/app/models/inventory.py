import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, Column, Float, UniqueConstraint
from sqlmodel import Field, SQLModel

from app.models.columns import (
    created_at_column,
    enum_column,
    fk,
    money_column,
    text_column,
    utcnow,
    uuid_pk,
)
from app.models.enums import IngredientUnit, MovementType


class Supplier(SQLModel, table=True):
    __tablename__ = "supplier"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, sa_column=uuid_pk())
    tenant_id: uuid.UUID = Field(sa_column=fk("tenant.id"))
    name: str = Field(max_length=255)
    contact_name: str = Field(default="", max_length=255)
    phone: str = Field(default="", max_length=20)
    email: str | None = Field(default=None, max_length=255)
    notes: str | None = Field(default=None, sa_column=text_column(nullable=True))


class Warehouse(SQLModel, table=True):
    __tablename__ = "warehouse"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, sa_column=uuid_pk())
    tenant_id: uuid.UUID = Field(sa_column=fk("tenant.id"))
    name: str = Field(max_length=255)
    is_primary: bool = Field(default=False)
    location_notes: str | None = Field(default=None, max_length=500)


class Ingredient(SQLModel, table=True):
    __tablename__ = "ingredient"
    __table_args__ = (
        CheckConstraint(
            "waste_factor >= 0 AND waste_factor < 0.95",
            name="ck_ingredient_waste_factor",
        ),
        CheckConstraint(
            "cooking_yield_factor >= 0.10 AND cooking_yield_factor <= 1.50",
            name="ck_ingredient_cooking_yield",
        ),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, sa_column=uuid_pk())
    tenant_id: uuid.UUID = Field(sa_column=fk("tenant.id"))
    supplier_id: uuid.UUID | None = Field(
        default=None,
        sa_column=fk("supplier.id", nullable=True, ondelete="SET NULL"),
    )
    name: str = Field(max_length=255)
    unit: IngredientUnit = Field(
        sa_column=enum_column(IngredientUnit, "ingredient_unit")
    )
    purchase_price: Decimal = Field(sa_column=money_column())
    sale_price: Decimal | None = Field(
        default=None, sa_column=money_column(nullable=True)
    )
    min_stock: float = Field(sa_column=Column(Float, nullable=False))
    max_stock: float = Field(sa_column=Column(Float, nullable=False))
    waste_factor: float = Field(sa_column=Column(Float, nullable=False))
    cooking_yield_factor: float = Field(sa_column=Column(Float, nullable=False))


class WarehouseStock(SQLModel, table=True):
    __tablename__ = "warehouse_stock"
    __table_args__ = (
        UniqueConstraint(
            "warehouse_id",
            "ingredient_id",
            name="uq_warehouse_stock_warehouse_ingredient",
        ),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, sa_column=uuid_pk())
    tenant_id: uuid.UUID = Field(sa_column=fk("tenant.id"))
    warehouse_id: uuid.UUID = Field(sa_column=fk("warehouse.id"))
    ingredient_id: uuid.UUID = Field(sa_column=fk("ingredient.id"))
    physical_stock: float = Field(
        default=0.0, sa_column=Column(Float, nullable=False, server_default="0")
    )
    committed_stock: float = Field(
        default=0.0, sa_column=Column(Float, nullable=False, server_default="0")
    )

    @property
    def available_stock(self) -> float:
        return self.physical_stock - self.committed_stock


class InventoryMovement(SQLModel, table=True):
    __tablename__ = "inventory_movement"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, sa_column=uuid_pk())
    tenant_id: uuid.UUID = Field(sa_column=fk("tenant.id"))
    warehouse_id: uuid.UUID = Field(sa_column=fk("warehouse.id"))
    ingredient_id: uuid.UUID = Field(sa_column=fk("ingredient.id"))
    movement_type: MovementType = Field(
        sa_column=enum_column(MovementType, "movement_type")
    )
    quantity: float = Field(sa_column=Column(Float, nullable=False))
    reference_id: uuid.UUID | None = Field(default=None)
    created_at: datetime = Field(default_factory=utcnow, sa_column=created_at_column())
