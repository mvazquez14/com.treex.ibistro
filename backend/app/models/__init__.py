from sqlmodel import SQLModel

from app.models.commerce import (
    DeliveryZone,
    Lead,
    PaymentReceipt,
    POSOrder,
    Quote,
    Reservation,
)
from app.models.enums import (
    EquipmentCategory,
    IngredientUnit,
    LeadSource,
    MovementType,
    OperationStatus,
    PaymentMethod,
    PaymentStatus,
    PricingType,
    QuoteStatus,
)
from app.models.equipment import EquipmentAsset, PackageEquipmentRule
from app.models.inventory import (
    Ingredient,
    InventoryMovement,
    Supplier,
    Warehouse,
    WarehouseStock,
)
from app.models.menu import (
    CateringPackage,
    MenuExtra,
    PackageGroupOption,
    PackageRecipeGroup,
    Recipe,
    RecipeItem,
)
from app.models.platform import PlatformAuditLog
from app.models.tenant import (
    ServiceCategory,
    ServiceScheduleSlot,
    Tenant,
    TenantPhoto,
)

__all__ = [
    "SQLModel",
    "CateringPackage",
    "DeliveryZone",
    "EquipmentAsset",
    "EquipmentCategory",
    "Ingredient",
    "IngredientUnit",
    "InventoryMovement",
    "Lead",
    "LeadSource",
    "MenuExtra",
    "MovementType",
    "OperationStatus",
    "POSOrder",
    "PackageEquipmentRule",
    "PackageGroupOption",
    "PackageRecipeGroup",
    "PaymentMethod",
    "PaymentReceipt",
    "PaymentStatus",
    "PlatformAuditLog",
    "PricingType",
    "Quote",
    "QuoteStatus",
    "Recipe",
    "RecipeItem",
    "Reservation",
    "ServiceCategory",
    "ServiceScheduleSlot",
    "Supplier",
    "Tenant",
    "TenantPhoto",
    "Warehouse",
    "WarehouseStock",
]
