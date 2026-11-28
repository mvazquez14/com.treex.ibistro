import uuid
from decimal import Decimal

from sqlalchemy import Boolean, Column, Float, Integer, UniqueConstraint
from sqlmodel import Field, SQLModel

from app.models.columns import enum_column, fk, money_column, text_column, uuid_pk
from app.models.enums import PricingType


class Recipe(SQLModel, table=True):
    __tablename__ = "recipe"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, sa_column=uuid_pk())
    tenant_id: uuid.UUID = Field(sa_column=fk("tenant.id"))
    name: str = Field(max_length=255)
    is_sub_recipe: bool = Field(default=False)
    portion_size: float = Field(sa_column=Column(Float, nullable=False))
    portion_unit: str = Field(max_length=20)


class RecipeItem(SQLModel, table=True):
    __tablename__ = "recipe_item"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, sa_column=uuid_pk())
    tenant_id: uuid.UUID = Field(sa_column=fk("tenant.id"))
    recipe_id: uuid.UUID = Field(sa_column=fk("recipe.id"))
    ingredient_id: uuid.UUID | None = Field(
        default=None,
        sa_column=fk("ingredient.id", nullable=True, ondelete="SET NULL"),
    )
    sub_recipe_id: uuid.UUID | None = Field(
        default=None,
        sa_column=fk("recipe.id", nullable=True, ondelete="SET NULL"),
    )
    net_qty_per_portion: float = Field(sa_column=Column(Float, nullable=False))


class CateringPackage(SQLModel, table=True):
    __tablename__ = "catering_package"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, sa_column=uuid_pk())
    tenant_id: uuid.UUID = Field(sa_column=fk("tenant.id"))
    category_id: uuid.UUID = Field(
        sa_column=fk("service_category.id", ondelete="RESTRICT")
    )
    name: str = Field(max_length=255)
    description: str = Field(default="", sa_column=text_column())
    photo_url: str | None = Field(default=None, max_length=2048)
    base_price_per_guest: Decimal = Field(sa_column=money_column())
    min_guests: int = Field(sa_column=Column(Integer, nullable=False))
    is_active: bool = Field(
        default=True, sa_column=Column(Boolean, nullable=False, server_default="true")
    )


class PackageRecipeGroup(SQLModel, table=True):
    __tablename__ = "package_recipe_group"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, sa_column=uuid_pk())
    tenant_id: uuid.UUID = Field(sa_column=fk("tenant.id"))
    package_id: uuid.UUID = Field(sa_column=fk("catering_package.id"))
    group_name: str = Field(max_length=255)
    min_choices: int = Field(
        default=1, sa_column=Column(Integer, nullable=False, server_default="1")
    )
    max_choices: int = Field(
        default=1, sa_column=Column(Integer, nullable=False, server_default="1")
    )
    is_fixed: bool = Field(default=False)


class PackageGroupOption(SQLModel, table=True):
    __tablename__ = "package_group_option"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, sa_column=uuid_pk())
    tenant_id: uuid.UUID = Field(sa_column=fk("tenant.id"))
    group_id: uuid.UUID = Field(sa_column=fk("package_recipe_group.id"))
    recipe_id: uuid.UUID = Field(sa_column=fk("recipe.id"))
    portions_per_guest: float = Field(
        default=1.0,
        sa_column=Column(Float, nullable=False, server_default="1"),
    )
    extra_price_per_guest: Decimal = Field(
        default=Decimal("0.00"),
        sa_column=money_column(),
    )


class MenuExtra(SQLModel, table=True):
    __tablename__ = "menu_extra"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, sa_column=uuid_pk())
    tenant_id: uuid.UUID = Field(sa_column=fk("tenant.id"))
    name: str = Field(max_length=255)
    ingredient_id: uuid.UUID | None = Field(
        default=None,
        sa_column=fk("ingredient.id", nullable=True, ondelete="SET NULL"),
    )
    recipe_id: uuid.UUID | None = Field(
        default=None,
        sa_column=fk("recipe.id", nullable=True, ondelete="SET NULL"),
    )
    unit_price: Decimal = Field(sa_column=money_column())
    pricing_type: PricingType = Field(
        sa_column=enum_column(PricingType, "pricing_type")
    )
    is_active: bool = Field(default=True)


class ExtraCategory(SQLModel, table=True):
    __tablename__ = "extra_category"
    __table_args__ = (
        UniqueConstraint("extra_id", "category_id", name="uq_extra_category"),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, sa_column=uuid_pk())
    tenant_id: uuid.UUID = Field(sa_column=fk("tenant.id"))
    extra_id: uuid.UUID = Field(sa_column=fk("menu_extra.id"))
    category_id: uuid.UUID = Field(
        sa_column=fk("service_category.id", ondelete="CASCADE")
    )
