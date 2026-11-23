from enum import StrEnum


class IngredientUnit(StrEnum):
    KG = "kg"
    LT = "lt"
    PZ = "pz"
    GR = "gr"
    ML = "ml"


class MovementType(StrEnum):
    PURCHASE_IN = "PURCHASE_IN"
    COMMIT_RESERVE = "COMMIT_RESERVE"
    COMMIT_RELEASE = "COMMIT_RELEASE"
    PRODUCTION_OUT = "PRODUCTION_OUT"
    POS_SALE_OUT = "POS_SALE_OUT"
    ADJUSTMENT = "ADJUSTMENT"


class EquipmentCategory(StrEnum):
    MANTELERIA = "Manteleria"
    MOBILIARIO = "Mobiliario"
    LOZA = "Loza"
    CALENTAMIENTO = "Calentamiento"
    CRISTALERIA = "Cristaleria"


class PricingType(StrEnum):
    PER_GUEST = "PER_GUEST"
    PER_UNIT = "PER_UNIT"


class LeadSource(StrEnum):
    MICRO_LANDING = "micro_landing"
    WHATSAPP_DIRECT = "whatsapp_direct"
    WHATSAPP_CONCIERGE = "whatsapp_concierge"
    MANUAL_DASHBOARD = "manual_dashboard"


class QuoteStatus(StrEnum):
    PENDING_REVIEW = "PENDING_REVIEW"
    SENT_TO_CLIENT = "SENT_TO_CLIENT"
    NEGOTIATING = "NEGOTIATING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class PaymentStatus(StrEnum):
    UNPAID = "UNPAID"
    PARTIAL_DEPOSIT = "PARTIAL_DEPOSIT"
    PAID_IN_FULL = "PAID_IN_FULL"


class OperationStatus(StrEnum):
    CONFIRMED = "CONFIRMED"
    IN_PREP = "IN_PREP"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


class PaymentMethod(StrEnum):
    TRANSFER = "TRANSFER"
    CASH = "CASH"
    CARD = "CARD"
