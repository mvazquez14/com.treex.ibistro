from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.enums import (
    EquipmentCategory,
    IngredientUnit,
    MovementType,
    PricingType,
)


class RecipeItemIn(BaseModel):
    ingredient_id: UUID | None = None
    sub_recipe_id: UUID | None = None
    net_qty_per_portion: float = Field(gt=0)


class RecipeItemRead(BaseModel):
    id: UUID
    ingredient_id: UUID | None
    sub_recipe_id: UUID | None
    label: str
    net_qty_per_portion: float


class RecipeIn(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    portion_size: float = Field(gt=0)
    portion_unit: str = Field(min_length=1, max_length=20)
    is_sub_recipe: bool = False


class RecipeUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    portion_size: float | None = Field(default=None, gt=0)
    portion_unit: str | None = Field(default=None, min_length=1, max_length=20)
    is_sub_recipe: bool | None = None


class RecipeRead(BaseModel):
    id: UUID
    name: str
    is_sub_recipe: bool
    portion_size: float
    portion_unit: str
    cost_per_portion: Decimal | None
    cost_note: str | None
    items: list[RecipeItemRead]


class PackageOptionIn(BaseModel):
    recipe_id: UUID
    portions_per_guest: float = Field(default=1, gt=0)
    extra_price_per_guest: Decimal = Decimal("0")


class PackageOptionRead(BaseModel):
    id: UUID
    recipe_id: UUID
    recipe_name: str
    portions_per_guest: float
    extra_price_per_guest: Decimal


class PackageGroupIn(BaseModel):
    group_name: str = Field(min_length=1, max_length=255)
    min_choices: int = Field(default=1, ge=0)
    max_choices: int = Field(default=1, ge=0)
    is_fixed: bool = False


class PackageGroupUpdate(BaseModel):
    group_name: str | None = Field(default=None, min_length=1, max_length=255)
    min_choices: int | None = Field(default=None, ge=0)
    max_choices: int | None = Field(default=None, ge=0)
    is_fixed: bool | None = None


class PackageGroupRead(BaseModel):
    id: UUID
    group_name: str
    min_choices: int
    max_choices: int
    is_fixed: bool
    options: list[PackageOptionRead]


class PackageIn(BaseModel):
    category_id: UUID
    name: str = Field(min_length=1, max_length=255)
    description: str = ""
    photo_url: str | None = None
    base_price_per_guest: Decimal
    min_guests: int = Field(ge=1)
    is_active: bool = True


class PackageUpdate(BaseModel):
    category_id: UUID | None = None
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    photo_url: str | None = None
    base_price_per_guest: Decimal | None = None
    min_guests: int | None = Field(default=None, ge=1)
    is_active: bool | None = None


class PackageRead(BaseModel):
    id: UUID
    category_id: UUID
    category_name: str
    name: str
    description: str
    photo_url: str | None
    base_price_per_guest: Decimal
    min_guests: int
    is_active: bool
    groups: list[PackageGroupRead]


class ExtraIn(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    ingredient_id: UUID | None = None
    recipe_id: UUID | None = None
    unit_price: Decimal
    pricing_type: PricingType
    is_active: bool = True


class ExtraUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    ingredient_id: UUID | None = None
    recipe_id: UUID | None = None
    unit_price: Decimal | None = None
    pricing_type: PricingType | None = None
    is_active: bool | None = None
    clear_ingredient: bool = False
    clear_recipe: bool = False


class ExtraRead(BaseModel):
    id: UUID
    name: str
    ingredient_id: UUID | None
    recipe_id: UUID | None
    link_label: str
    unit_price: Decimal
    pricing_type: PricingType
    is_active: bool


class QuoteExtraIn(BaseModel):
    extra_id: UUID
    quantity: float = Field(gt=0)


class QuoteIn(BaseModel):
    guest_count: int = Field(ge=1)
    selected_options: dict[UUID, list[UUID]] = {}
    extras: list[QuoteExtraIn] = []


class NeedRead(BaseModel):
    ingredient_id: UUID
    ingredient_name: str
    net_qty: float
    gross_qty: float
    cost: Decimal


class QuoteRead(BaseModel):
    cogs: Decimal
    price: Decimal
    price_per_guest: Decimal
    explosion: list[NeedRead]


class CategoryRead(BaseModel):
    id: UUID
    name: str
    slug: str


class MenuScreen(BaseModel):
    recipes: list[RecipeRead]
    packages: list[PackageRead]
    extras: list[ExtraRead]
    ingredients: list[IngredientRead]
    categories: list[CategoryRead]


class SupplierIn(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    contact_name: str = ""
    phone: str = ""
    email: str | None = None
    notes: str | None = None


class SupplierUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    contact_name: str | None = None
    phone: str | None = None
    email: str | None = None
    notes: str | None = None


class SupplierRead(BaseModel):
    id: UUID
    name: str
    contact_name: str
    phone: str
    email: str | None
    notes: str | None


class WarehouseIn(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    is_primary: bool = False
    location_notes: str | None = None


class WarehouseUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    is_primary: bool | None = None
    location_notes: str | None = None


class WarehouseRead(BaseModel):
    id: UUID
    name: str
    is_primary: bool
    location_notes: str | None


class IngredientIn(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    unit: IngredientUnit
    purchase_price: Decimal
    sale_price: Decimal | None = None
    min_stock: float = 0
    max_stock: float = 0
    waste_factor: float = 0
    cooking_yield_factor: float = 1
    supplier_id: UUID | None = None


class IngredientUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    unit: IngredientUnit | None = None
    purchase_price: Decimal | None = None
    sale_price: Decimal | None = None
    min_stock: float | None = None
    max_stock: float | None = None
    waste_factor: float | None = None
    cooking_yield_factor: float | None = None
    supplier_id: UUID | None = None
    clear_supplier: bool = False
    clear_sale_price: bool = False


class IngredientRead(BaseModel):
    id: UUID
    supplier_id: UUID | None
    supplier_name: str | None
    name: str
    unit: IngredientUnit
    purchase_price: Decimal
    sale_price: Decimal | None
    min_stock: float
    max_stock: float
    waste_factor: float
    cooking_yield_factor: float


class StockRead(BaseModel):
    warehouse_id: UUID
    warehouse_name: str
    ingredient_id: UUID
    ingredient_name: str
    unit: IngredientUnit
    physical_stock: float
    committed_stock: float
    available_stock: float


class MovementIn(BaseModel):
    warehouse_id: UUID
    ingredient_id: UUID
    movement_type: MovementType
    quantity: float
    reference_id: UUID | None = None


class CommitIn(BaseModel):
    recipe_id: UUID
    portions: float = Field(default=1, gt=0)
    reference_id: UUID | None = None


class MovementRead(BaseModel):
    id: UUID
    warehouse_id: UUID
    warehouse_name: str
    ingredient_id: UUID
    ingredient_name: str
    movement_type: MovementType
    quantity: float
    reference_id: UUID | None
    created_at: str


class WarehouseScreen(BaseModel):
    suppliers: list[SupplierRead]
    warehouses: list[WarehouseRead]
    ingredients: list[IngredientRead]
    stock: list[StockRead]
    kardex: list[MovementRead]


class AssetIn(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    category: EquipmentCategory
    total_stock: int = Field(ge=0)
    rental_price_per_unit: Decimal = Decimal("0")
    replacement_cost: Decimal


class AssetUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    category: EquipmentCategory | None = None
    total_stock: int | None = Field(default=None, ge=0)
    rental_price_per_unit: Decimal | None = None
    replacement_cost: Decimal | None = None


class AssetRead(BaseModel):
    id: UUID
    name: str
    category: EquipmentCategory
    total_stock: int
    rental_price_per_unit: Decimal
    replacement_cost: Decimal


class RuleIn(BaseModel):
    package_id: UUID
    asset_id: UUID
    guests_per_unit: int = Field(ge=1)


class RuleUpdate(BaseModel):
    guests_per_unit: int = Field(ge=1)


class RuleRead(BaseModel):
    id: UUID
    package_id: UUID
    package_name: str
    asset_id: UUID
    asset_name: str
    guests_per_unit: int
    units_for_guests: int


class PackageChoice(BaseModel):
    id: UUID
    name: str


class EquipmentScreen(BaseModel):
    assets: list[AssetRead]
    rules: list[RuleRead]
    packages: list[PackageChoice]
    guests: int


MenuScreen.model_rebuild()
