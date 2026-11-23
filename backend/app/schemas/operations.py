"""Reservations, point of sale, and the provider reports."""

from datetime import date
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.enums import OperationStatus, PaymentMethod, PaymentStatus

METHOD_LABELS: dict[PaymentMethod, str] = {
    PaymentMethod.CASH: "Efectivo",
    PaymentMethod.CARD: "Tarjeta",
    PaymentMethod.TRANSFER: "Transferencia",
}
PAYMENT_LABELS: dict[PaymentStatus, str] = {
    PaymentStatus.UNPAID: "Sin pago",
    PaymentStatus.PARTIAL_DEPOSIT: "Anticipo",
    PaymentStatus.PAID_IN_FULL: "Liquidada",
}
OPERATION_LABELS: dict[OperationStatus, str] = {
    OperationStatus.CONFIRMED: "Confirmada",
    OperationStatus.IN_PREP: "En preparación",
    OperationStatus.COMPLETED: "Cerrada",
    OperationStatus.CANCELLED: "Cancelada",
}


class ReceiptIn(BaseModel):
    amount: Decimal
    payment_method: PaymentMethod
    receipt_file_url: str | None = None
    is_verified: bool = False


class ReceiptRead(BaseModel):
    id: UUID
    amount: Decimal
    payment_method: PaymentMethod
    method_label: str
    receipt_file_url: str | None
    is_verified: bool


class ReservationCard(BaseModel):
    id: UUID
    customer_name: str
    customer_phone: str
    venue_address: str
    event_date: date
    slot_label: str
    guest_count: int
    total_amount: Decimal
    paid_amount: Decimal
    balance: Decimal
    payment_status: PaymentStatus
    payment_label: str
    operation_status: OperationStatus
    operation_label: str
    special_requests: str | None
    receipts: list[ReceiptRead]


class ReservationsScreen(BaseModel):
    reservations: list[ReservationCard]


class PosLineIn(BaseModel):
    kind: Literal["ingredient", "extra", "package"]
    item_id: UUID
    quantity: float = Field(gt=0)


class PosSaleIn(BaseModel):
    warehouse_id: UUID
    payment_method: PaymentMethod
    apply_tax: bool = False
    tax_rate: Decimal | None = None
    reservation_id: UUID | None = None
    lines: list[PosLineIn]


class PosLineRead(BaseModel):
    kind: str
    item_id: UUID
    name: str
    quantity: str
    amount: Decimal


class PosOrderRead(BaseModel):
    id: UUID
    warehouse_id: UUID
    reservation_id: UUID | None
    payment_method: PaymentMethod
    method_label: str
    subtotal: Decimal
    tax_amount: Decimal
    total_amount: Decimal
    lines: list[PosLineRead]


class PosProduct(BaseModel):
    kind: Literal["ingredient", "extra", "package"]
    id: UUID
    name: str
    detail: str
    unit_price: Decimal


class PosWarehouse(BaseModel):
    id: UUID
    name: str
    is_primary: bool


class PosReservationOption(BaseModel):
    id: UUID
    label: str


class PosScreen(BaseModel):
    tax_rate: Decimal
    warehouses: list[PosWarehouse]
    products: list[PosProduct]
    reservations: list[PosReservationOption]
    orders: list[PosOrderRead]


class ProfitRow(BaseModel):
    reservation_id: UUID
    customer_name: str
    event_date: date
    revenue: Decimal
    food_cost: Decimal
    waiter_cost: Decimal
    freight: Decimal
    operating_cost: Decimal
    margin: Decimal
    margin_percent: Decimal


class PurchaseLine(BaseModel):
    supplier_name: str
    ingredient_name: str
    unit: str
    needed_qty: float
    available_qty: float
    buy_qty: float


class RestockAlert(BaseModel):
    ingredient_name: str
    available_qty: float
    min_stock: float


class OccupancyCell(BaseModel):
    event_date: date
    slot_label: str
    events: int
    capacity: int


class EquipmentPressure(BaseModel):
    event_date: date
    asset_name: str
    units: int
    total_stock: int


class CashLine(BaseModel):
    method_label: str
    pos_total: Decimal
    receipt_total: Decimal


class PendingBalance(BaseModel):
    customer_name: str
    event_date: date
    balance: Decimal


class ProviderReports(BaseModel):
    profitability: list[ProfitRow]
    purchases: list[PurchaseLine]
    restock: list[RestockAlert]
    occupancy: list[OccupancyCell]
    equipment: list[EquipmentPressure]
    cash: list[CashLine]
    pending: list[PendingBalance]
    generated_on: date
