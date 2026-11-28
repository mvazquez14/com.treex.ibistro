"""Reservations, counter sales, and the five provider reports."""

from datetime import date, timedelta
from decimal import Decimal

from fastapi.testclient import TestClient

from app.core.config import settings
from app.models import ServiceCategory
from tests.memory_db import MemorySession


def _login(client: TestClient) -> None:
    response = client.get("/api/auth/callback", params={"code": "demo"})
    assert response.status_code == 302


def _money(value: object) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.01"))


def _tune(client: TestClient, memory_db: MemorySession) -> str:
    _login(client)
    tenant = next(iter(memory_db.tenants.values()))
    tenant.min_guests = 1
    tenant.max_guests = 300
    tenant.waiter_cost_per_event = Decimal("0.00")
    tenant.default_tax_rate = 0
    tenant.show_prices_public = True
    tenant.has_active_plan = True
    tenant.whatsapp_phone = "+5213312345678"
    tenant.max_concurrent_events_per_slot = 5
    return str(client.get("/api/auth/session").json()["slug"])


def _stock(client: TestClient, name: str) -> dict[str, object]:
    rows = client.get("/api/v1/warehouses/stock").json()
    return next(row for row in rows if row["ingredient_name"] == name)


def test_reservations_pos_and_provider_reports(
    client: TestClient, memory_db: MemorySession, monkeypatch: object
) -> None:
    from pytest import MonkeyPatch

    patch: MonkeyPatch = monkeypatch  # type: ignore[assignment]
    patch.setattr(settings, "SMTP_HOST", "")
    patch.setattr("app.services.quoting.send_email", lambda **_kwargs: None)
    slug = _tune(client, memory_db)
    day = date.today() + timedelta(days=1)
    later = day + timedelta(days=1)

    supplier = client.post("/api/v1/warehouses/suppliers", json={"name": "Abarrotes"})
    assert supplier.status_code == 201
    warehouse = client.post(
        "/api/v1/warehouses",
        json={"name": "Central", "is_primary": True},
    )
    assert warehouse.status_code == 201, warehouse.text
    warehouse_id = warehouse.json()["id"]
    pollo = client.post(
        "/api/v1/warehouses/ingredients",
        json={
            "name": "Pollo",
            "unit": "kg",
            "purchase_price": "80.00",
            "supplier_id": supplier.json()["id"],
            "waste_factor": 0,
            "cooking_yield_factor": 1,
            "min_stock": 0,
            "max_stock": 20,
        },
    )
    assert pollo.status_code == 201, pollo.text
    pollo_id = pollo.json()["id"]
    sal = client.post(
        "/api/v1/warehouses/ingredients",
        json={
            "name": "Sal",
            "unit": "kg",
            "purchase_price": "10.00",
            "min_stock": 5,
            "max_stock": 10,
        },
    )
    assert sal.status_code == 201, sal.text
    agua = client.post(
        "/api/v1/warehouses/ingredients",
        json={
            "name": "Agua",
            "unit": "pz",
            "purchase_price": "8.00",
            "sale_price": "25.00",
            "waste_factor": 0,
            "cooking_yield_factor": 1,
            "min_stock": 0,
            "max_stock": 20,
        },
    )
    assert agua.status_code == 201, agua.text
    agua_id = agua.json()["id"]
    bought = client.post(
        "/api/v1/warehouses/movements",
        json={
            "warehouse_id": warehouse_id,
            "ingredient_id": pollo_id,
            "movement_type": "PURCHASE_IN",
            "quantity": 2,
        },
    )
    assert bought.status_code == 201, bought.text

    recipe = client.post(
        "/api/v1/menu/recipes",
        json={"name": "Guiso", "portion_size": 1, "portion_unit": "porción"},
    )
    assert recipe.status_code == 201, recipe.text
    recipe_id = recipe.json()["id"]
    item = client.post(
        f"/api/v1/menu/recipes/{recipe_id}/items",
        json={"ingredient_id": pollo_id, "net_qty_per_portion": 1},
    )
    assert item.status_code == 201, item.text
    category = ServiceCategory(name="Tacos", slug="tacos-ops", icon="")
    memory_db.add(category)
    package = client.post(
        "/api/v1/menu/packages",
        json={
            "category_id": str(category.id),
            "name": "Taquiza",
            "base_price_per_guest": "100.00",
            "min_guests": 1,
        },
    )
    assert package.status_code == 201, package.text
    package_id = package.json()["id"]
    group = client.post(
        f"/api/v1/menu/packages/{package_id}/groups",
        json={
            "group_name": "Incluido",
            "is_fixed": True,
            "min_choices": 1,
            "max_choices": 1,
        },
    )
    assert group.status_code == 201, group.text
    group_id = group.json()["groups"][0]["id"]
    option = client.post(
        f"/api/v1/menu/groups/{group_id}/options",
        json={"recipe_id": recipe_id, "portions_per_guest": 1},
    )
    assert option.status_code == 201, option.text
    asset = client.post(
        "/api/v1/equipment/assets",
        json={
            "name": "Mantel",
            "category": "Manteleria",
            "total_stock": 1,
            "rental_price_per_unit": "0",
            "replacement_cost": "100",
        },
    )
    assert asset.status_code == 201, asset.text
    rule = client.post(
        "/api/v1/equipment/rules",
        json={
            "package_id": package_id,
            "asset_id": asset.json()["id"],
            "guests_per_unit": 2,
        },
    )
    assert rule.status_code == 201, rule.text
    choice = client.post(
        "/api/v1/menu/packages",
        json={
            "category_id": str(category.id),
            "name": "Eleccion",
            "base_price_per_guest": "80.00",
            "min_guests": 1,
        },
    )
    assert choice.status_code == 201, choice.text
    choice_id = choice.json()["id"]
    choice_group = client.post(
        f"/api/v1/menu/packages/{choice_id}/groups",
        json={
            "group_name": "Guiso",
            "is_fixed": False,
            "min_choices": 1,
            "max_choices": 1,
        },
    )
    assert choice_group.status_code == 201, choice_group.text
    banquet = client.post(
        "/api/v1/menu/packages",
        json={
            "category_id": str(category.id),
            "name": "Banquete",
            "base_price_per_guest": "100.00",
            "min_guests": 8,
        },
    )
    assert banquet.status_code == 201, banquet.text
    agua_extra = client.post(
        "/api/v1/menu/extras",
        json={
            "name": "Agua extra",
            "ingredient_id": agua_id,
            "unit_price": "15.00",
            "pricing_type": "PER_UNIT",
        },
    )
    assert agua_extra.status_code == 201, agua_extra.text
    recipe_extra = client.post(
        "/api/v1/menu/extras",
        json={
            "name": "Porción extra",
            "recipe_id": recipe_id,
            "unit_price": "10.00",
            "pricing_type": "PER_UNIT",
        },
    )
    assert recipe_extra.status_code == 201, recipe_extra.text
    service = client.post(
        "/api/v1/menu/extras",
        json={
            "name": "Servicio",
            "unit_price": "40.00",
            "pricing_type": "PER_GUEST",
        },
    )
    assert service.status_code == 201, service.text
    retired = client.post(
        "/api/v1/menu/extras",
        json={
            "name": "Retirado",
            "unit_price": "5.00",
            "pricing_type": "PER_UNIT",
        },
    )
    assert retired.status_code == 201, retired.text
    hidden = client.patch(
        f"/api/v1/menu/extras/{retired.json()['id']}",
        json={"is_active": False},
    )
    assert hidden.status_code == 200, hidden.text

    slot = client.post(
        "/api/v1/schedule/slots",
        json={
            "day_of_week": day.weekday(),
            "start_time": "10:00",
            "end_time": "12:00",
            "is_active": True,
        },
    )
    assert slot.status_code == 201, slot.text
    later_slot = client.post(
        "/api/v1/schedule/slots",
        json={
            "day_of_week": later.weekday(),
            "start_time": "10:00",
            "end_time": "12:00",
            "is_active": True,
        },
    )
    assert later_slot.status_code == 201, later_slot.text
    quote = client.post(
        f"/api/v1/public/{slug}/quotes",
        json={
            "package_id": package_id,
            "event_date": day.isoformat(),
            "slot_id": slot.json()["id"],
            "start_time": "10:00",
            "guest_count": 2,
            "full_name": "Ana López",
            "phone": "+5213311111111",
            "whatsapp_phone": "+5213311111111",
            "venue_address": "Av. México 10",
        },
    )
    assert quote.status_code == 201, quote.text
    assert _money(quote.json()["total_amount"]) == Decimal("200.00")
    converted = client.post(f"/api/v1/quotes/{quote.json()['id']}/convert")
    assert converted.status_code == 200, converted.text
    reservation_id = converted.json()["reservation_id"]

    catalog = client.get("/api/v1/pos")
    assert catalog.status_code == 200
    names = {row["name"] for row in catalog.json()["products"]}
    assert "Agua" in names
    assert "Taquiza" in names
    assert "Banquete" in names
    assert "Eleccion" not in names
    assert "Pollo" not in names
    assert "Retirado" not in names
    service_row = next(
        row for row in catalog.json()["products"] if row["name"] == "Servicio"
    )
    assert service_row["detail"] == "por invitado"

    early = client.get("/api/v1/reports")
    assert early.status_code == 200
    body = early.json()
    profit = body["profitability"][0]
    assert profit["customer_name"] == "Ana López"
    assert _money(profit["revenue"]) == Decimal("200.00")
    assert _money(profit["food_cost"]) == Decimal("160.00")
    assert _money(profit["margin"]) == Decimal("40.00")
    assert _money(profit["margin_percent"]) == Decimal("20.00")
    purchase = body["purchases"][0]
    assert purchase["supplier_name"] == "Abarrotes"
    assert purchase["ingredient_name"] == "Pollo"
    assert purchase["buy_qty"] == 2
    assert any(row["ingredient_name"] == "Sal" for row in body["restock"])
    assert body["occupancy"][0]["events"] == 1
    assert body["occupancy"][0]["capacity"] == 5
    assert body["equipment"][0]["asset_name"] == "Mantel"
    assert _money(body["pending"][0]["balance"]) == Decimal("200.00")
    assert all(_money(row["pos_total"]) == 0 for row in body["cash"])

    refused = client.post(
        "/api/v1/pos/orders",
        json={
            "warehouse_id": warehouse_id,
            "payment_method": "CASH",
            "lines": [{"kind": "package", "item_id": package_id, "quantity": 1}],
        },
    )
    assert refused.status_code == 409
    assert "venta" in refused.json()["detail"]

    topped = client.post(
        "/api/v1/warehouses/movements",
        json={
            "warehouse_id": warehouse_id,
            "ingredient_id": pollo_id,
            "movement_type": "PURCHASE_IN",
            "quantity": 10,
        },
    )
    assert topped.status_code == 201, topped.text
    agua_in = client.post(
        "/api/v1/warehouses/movements",
        json={
            "warehouse_id": warehouse_id,
            "ingredient_id": agua_id,
            "movement_type": "PURCHASE_IN",
            "quantity": 10,
        },
    )
    assert agua_in.status_code == 201, agua_in.text

    desk = client.get("/api/v1/reservations")
    assert desk.status_code == 200
    assert desk.json()["reservations"][0]["customer_name"] == "Ana López"
    assert _money(desk.json()["reservations"][0]["balance"]) == Decimal("200.00")
    bad_amount = client.post(
        f"/api/v1/reservations/{reservation_id}/receipts",
        json={"amount": "no", "payment_method": "TRANSFER"},
    )
    assert bad_amount.status_code == 422
    bad_method = client.post(
        f"/api/v1/reservations/{reservation_id}/receipts",
        json={"amount": "10", "payment_method": "CHEQUE"},
    )
    assert bad_method.status_code == 422
    first = client.post(
        f"/api/v1/reservations/{reservation_id}/receipts",
        json={
            "amount": "100.00",
            "payment_method": "TRANSFER",
            "receipt_file_url": "https://cdn.example/pago.jpg",
            "is_verified": True,
        },
    )
    assert first.status_code == 200
    assert first.json()["payment_label"] == "Anticipo"
    assert _money(first.json()["paid_amount"]) == Decimal("100.00")
    assert (
        first.json()["receipts"][0]["receipt_file_url"]
        == "https://cdn.example/pago.jpg"
    )

    listed = client.get("/api/v1/reservations")
    assert listed.status_code == 200
    card = listed.json()["reservations"][0]
    assert _money(card["balance"]) == Decimal("100.00")
    second = client.post(
        f"/api/v1/reservations/{reservation_id}/receipts",
        json={"amount": "50.00", "payment_method": "CASH", "is_verified": True},
    )
    assert second.status_code == 200
    assert _money(second.json()["paid_amount"]) == Decimal("150.00")
    cash_receipt = next(
        row["id"]
        for row in second.json()["receipts"]
        if row["payment_method"] == "CASH"
    )
    removed = client.delete(
        f"/api/v1/reservations/{reservation_id}/receipts/{cash_receipt}"
    )
    assert removed.status_code == 200
    assert _money(removed.json()["paid_amount"]) == Decimal("100.00")
    pending_receipt = client.post(
        f"/api/v1/reservations/{reservation_id}/receipts",
        json={
            "amount": "100.00",
            "payment_method": "TRANSFER",
            "receipt_file_url": "nota",
            "is_verified": False,
        },
    )
    assert pending_receipt.status_code == 422
    assert "liga" in pending_receipt.json()["detail"]
    pending_receipt = client.post(
        f"/api/v1/reservations/{reservation_id}/receipts",
        json={"amount": "100.00", "payment_method": "TRANSFER", "is_verified": False},
    )
    assert pending_receipt.status_code == 200
    assert _money(pending_receipt.json()["balance"]) == Decimal("100.00")
    open_receipt = next(
        row["id"]
        for row in pending_receipt.json()["receipts"]
        if not row["is_verified"]
    )
    verified = client.post(
        f"/api/v1/reservations/{reservation_id}/receipts/{open_receipt}/verify"
    )
    assert verified.status_code == 200
    assert verified.json()["payment_label"] == "Liquidada"
    again = client.post(
        f"/api/v1/reservations/{reservation_id}/receipts/{open_receipt}/verify"
    )
    assert again.status_code == 200
    assert again.json()["payment_status"] == "PAID_IN_FULL"
    over = client.post(
        f"/api/v1/reservations/{reservation_id}/receipts",
        json={"amount": "10.00", "payment_method": "CARD", "is_verified": True},
    )
    assert over.status_code == 422
    assert "liquidada" in over.json()["detail"]
    reopened = client.delete(
        f"/api/v1/reservations/{reservation_id}/receipts/{open_receipt}"
    )
    assert reopened.status_code == 200
    assert reopened.json()["payment_label"] == "Anticipo"
    zero = client.post(
        f"/api/v1/reservations/{reservation_id}/receipts",
        json={"amount": "0", "payment_method": "CASH", "is_verified": True},
    )
    assert zero.status_code == 422
    assert "mayor a cero" in zero.json()["detail"]
    negative = client.post(
        f"/api/v1/reservations/{reservation_id}/receipts",
        json={"amount": "-1", "payment_method": "CASH", "is_verified": True},
    )
    assert negative.status_code == 422
    missing = client.delete(
        f"/api/v1/reservations/{reservation_id}/receipts/"
        "00000000-0000-0000-0000-000000000000"
    )
    assert missing.status_code == 404
    assert "comprobante" in missing.json()["detail"]

    prepared = client.post(f"/api/v1/reservations/{reservation_id}/prepare")
    assert prepared.status_code == 200
    assert prepared.json()["operation_status"] == "IN_PREP"
    blocked_prep = client.post(f"/api/v1/reservations/{reservation_id}/prepare")
    assert blocked_prep.status_code == 409
    assert "preparar" in blocked_prep.json()["detail"]

    counter = client.post(
        "/api/v1/pos/orders",
        json={
            "warehouse_id": warehouse_id,
            "payment_method": "CASH",
            "lines": [{"kind": "ingredient", "item_id": agua_id, "quantity": 1}],
        },
    )
    assert counter.status_code == 200, counter.text
    assert _money(counter.json()["total_amount"]) == Decimal("25.00")
    assert counter.json()["method_label"] == "Efectivo"
    empty = client.post(
        "/api/v1/pos/orders",
        json={"warehouse_id": warehouse_id, "payment_method": "CASH", "lines": []},
    )
    assert empty.status_code == 422
    assert "producto" in empty.json()["detail"]
    bad_qty = client.post(
        "/api/v1/pos/orders",
        json={
            "warehouse_id": warehouse_id,
            "payment_method": "CASH",
            "lines": [{"kind": "ingredient", "item_id": agua_id, "quantity": "abc"}],
        },
    )
    assert bad_qty.status_code == 422
    bad_kind = client.post(
        "/api/v1/pos/orders",
        json={
            "warehouse_id": warehouse_id,
            "payment_method": "CASH",
            "lines": [{"kind": "nope", "item_id": agua_id, "quantity": 1}],
        },
    )
    assert bad_kind.status_code == 422
    bad_id = client.post(
        "/api/v1/pos/orders",
        json={
            "warehouse_id": warehouse_id,
            "payment_method": "CASH",
            "lines": [
                {
                    "kind": "ingredient",
                    "item_id": "not-a-uuid",
                    "quantity": 1,
                }
            ],
        },
    )
    assert bad_id.status_code == 422
    taxed = client.post(
        "/api/v1/pos/orders",
        json={
            "warehouse_id": warehouse_id,
            "payment_method": "CARD",
            "apply_tax": True,
            "tax_rate": "0.16",
            "lines": [
                {"kind": "extra", "item_id": service.json()["id"], "quantity": 1}
            ],
        },
    )
    assert taxed.status_code == 200, taxed.text
    assert _money(taxed.json()["tax_amount"]) == Decimal("6.40")
    assert _money(taxed.json()["total_amount"]) == Decimal("46.40")
    transferred = client.post(
        "/api/v1/pos/orders",
        json={
            "warehouse_id": warehouse_id,
            "payment_method": "TRANSFER",
            "lines": [
                {"kind": "extra", "item_id": agua_extra.json()["id"], "quantity": 2}
            ],
        },
    )
    assert transferred.status_code == 200, transferred.text
    assert _money(transferred.json()["total_amount"]) == Decimal("30.00")
    event_sale = client.post(
        "/api/v1/pos/orders",
        json={
            "warehouse_id": warehouse_id,
            "payment_method": "CASH",
            "reservation_id": reservation_id,
            "lines": [
                {"kind": "package", "item_id": package_id, "quantity": 1},
                {"kind": "extra", "item_id": recipe_extra.json()["id"], "quantity": 1},
            ],
        },
    )
    assert event_sale.status_code == 200, event_sale.text
    assert _money(event_sale.json()["total_amount"]) == Decimal("110.00")
    assert event_sale.json()["reservation_id"] == reservation_id
    short = client.post(
        "/api/v1/pos/orders",
        json={
            "warehouse_id": warehouse_id,
            "payment_method": "CASH",
            "lines": [{"kind": "ingredient", "item_id": agua_id, "quantity": 100}],
        },
    )
    assert short.status_code == 409
    unsold = client.post(
        "/api/v1/pos/orders",
        json={
            "warehouse_id": warehouse_id,
            "payment_method": "CASH",
            "lines": [{"kind": "ingredient", "item_id": pollo_id, "quantity": 1}],
        },
    )
    assert unsold.status_code == 422
    assert "precio de venta" in unsold.json()["detail"]
    whole = client.post(
        "/api/v1/pos/orders",
        json={
            "warehouse_id": warehouse_id,
            "payment_method": "CASH",
            "lines": [
                {"kind": "package", "item_id": banquet.json()["id"], "quantity": 1.5}
            ],
        },
    )
    assert whole.status_code == 422
    assert "entero" in whole.json()["detail"]
    minimum = client.post(
        "/api/v1/pos/orders",
        json={
            "warehouse_id": warehouse_id,
            "payment_method": "CASH",
            "lines": [
                {"kind": "package", "item_id": banquet.json()["id"], "quantity": 1}
            ],
        },
    )
    assert minimum.status_code == 422
    assert "8" in minimum.json()["detail"]
    choose = client.post(
        "/api/v1/pos/orders",
        json={
            "warehouse_id": warehouse_id,
            "payment_method": "CASH",
            "lines": [{"kind": "package", "item_id": choice_id, "quantity": 1}],
        },
    )
    assert choose.status_code == 422
    assert "opciones" in choose.json()["detail"]
    gone = client.post(
        "/api/v1/pos/orders",
        json={
            "warehouse_id": warehouse_id,
            "payment_method": "CASH",
            "lines": [
                {"kind": "extra", "item_id": retired.json()["id"], "quantity": 1}
            ],
        },
    )
    assert gone.status_code == 422
    assert "disponible" in gone.json()["detail"]
    unknown_warehouse = client.post(
        "/api/v1/pos/orders",
        json={
            "warehouse_id": "00000000-0000-0000-0000-000000000000",
            "payment_method": "CASH",
            "lines": [{"kind": "ingredient", "item_id": agua_id, "quantity": 1}],
        },
    )
    assert unknown_warehouse.status_code == 404

    assert _stock(client, "Agua")["physical_stock"] == 7
    assert _stock(client, "Pollo")["physical_stock"] == 10
    assert _stock(client, "Pollo")["committed_stock"] == 2

    closed = client.post(f"/api/v1/reservations/{reservation_id}/close")
    assert closed.status_code == 200, closed.text
    assert closed.json()["operation_status"] == "COMPLETED"
    assert _stock(client, "Pollo")["physical_stock"] == 8
    assert _stock(client, "Pollo")["committed_stock"] == 0
    closed_again = client.post(f"/api/v1/reservations/{reservation_id}/close")
    assert closed_again.status_code == 409
    assert "cerrada" in closed_again.json()["detail"]
    shipped = client.post(f"/api/v1/reservations/{reservation_id}/cancel")
    assert shipped.status_code == 409
    assert "surtió" in shipped.json()["detail"]
    shipped_page = client.post(f"/api/v1/reservations/{reservation_id}/cancel")
    assert shipped_page.status_code == 409
    unknown = client.post(
        "/api/v1/reservations/00000000-0000-0000-0000-000000000000/close"
    )
    assert unknown.status_code == 404

    second_quote = client.post(
        f"/api/v1/public/{slug}/quotes",
        json={
            "package_id": package_id,
            "event_date": later.isoformat(),
            "slot_id": later_slot.json()["id"],
            "start_time": "10:00",
            "guest_count": 2,
            "full_name": "Luis Pérez",
            "phone": "+5213311111112",
            "whatsapp_phone": "+5213311111112",
            "venue_address": "Av. México 20",
        },
    )
    assert second_quote.status_code == 201, second_quote.text
    second = client.post(f"/api/v1/quotes/{second_quote.json()['id']}/convert")
    assert second.status_code == 200, second.text
    second_id = second.json()["reservation_id"]
    assert _stock(client, "Pollo")["committed_stock"] == 2
    deposit = client.post(
        f"/api/v1/reservations/{second_id}/receipts",
        json={"amount": "150.00", "payment_method": "TRANSFER", "is_verified": False},
    )
    assert deposit.status_code == 200, deposit.text
    extra_receipt = client.post(
        f"/api/v1/reservations/{second_id}/receipts",
        json={"amount": "100.00", "payment_method": "CARD", "is_verified": False},
    )
    assert extra_receipt.status_code == 200, extra_receipt.text
    deposit_id = next(
        row["id"]
        for row in extra_receipt.json()["receipts"]
        if row["payment_method"] == "TRANSFER"
    )
    card_id = next(
        row["id"]
        for row in extra_receipt.json()["receipts"]
        if row["payment_method"] == "CARD"
    )
    accepted = client.post(
        f"/api/v1/reservations/{second_id}/receipts/{deposit_id}/verify"
    )
    assert accepted.status_code == 200
    assert _money(accepted.json()["paid_amount"]) == Decimal("150.00")
    rejected = client.post(
        f"/api/v1/reservations/{second_id}/receipts/{card_id}/verify"
    )
    assert rejected.status_code == 422
    assert "saldo" in rejected.json()["detail"]
    still = client.get("/api/v1/reservations").json()["reservations"]
    luis = next(row for row in still if row["id"] == second_id)
    assert _money(luis["paid_amount"]) == Decimal("150.00")
    cancelled = client.post(f"/api/v1/reservations/{second_id}/cancel")
    assert cancelled.status_code == 200
    assert cancelled.json()["operation_status"] == "CANCELLED"
    assert _stock(client, "Pollo")["physical_stock"] == 8
    assert _stock(client, "Pollo")["committed_stock"] == 0
    cancelled_again = client.post(f"/api/v1/reservations/{second_id}/cancel")
    assert cancelled_again.status_code == 409
    assert "cancelada" in cancelled_again.json()["detail"]
    linked = client.post(
        "/api/v1/pos/orders",
        json={
            "warehouse_id": warehouse_id,
            "payment_method": "CASH",
            "reservation_id": second_id,
            "lines": [
                {"kind": "extra", "item_id": service.json()["id"], "quantity": 1}
            ],
        },
    )
    assert linked.status_code == 409
    assert "cancelada" in linked.json()["detail"]

    final = client.get("/api/v1/reports")
    assert final.status_code == 200
    report = final.json()
    assert len(report["profitability"]) == 1
    assert report["purchases"] == []
    assert [row["ingredient_name"] for row in report["restock"]] == ["Sal"]
    assert len(report["occupancy"]) == 1
    assert report["equipment"][0]["asset_name"] == "Mantel"
    assert [row["customer_name"] for row in report["pending"]] == ["Ana López"]
    assert _money(report["pending"][0]["balance"]) == Decimal("100.00")
    cash = {row["method_label"]: row for row in report["cash"]}
    assert _money(cash["Efectivo"]["pos_total"]) == Decimal("135.00")
    assert _money(cash["Tarjeta"]["pos_total"]) == Decimal("46.40")
    assert _money(cash["Transferencia"]["pos_total"]) == Decimal("30.00")
    assert _money(cash["Transferencia"]["receipt_total"]) == Decimal("250.00")
    shell = client.get("/dashboard/reports")
    assert shell.status_code == 200
    assert 'lang="es"' in shell.text
    assert "iBistro" in shell.text
