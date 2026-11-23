"""Public landing, quote wizard, PDF, and reservation stock."""

import sys
import types
from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.core.config import settings
from app.models import (
    OperationStatus,
    Quote,
    QuoteStatus,
    Reservation,
    ServiceCategory,
)
from app.services.pdf_quote import QuoteDocument, _pesos, render_quote_pdf
from app.services.schedule_catalog import parse_clock, parse_day
from tests.memory_db import MemorySession


def _login(client: TestClient) -> None:
    response = client.get("/api/auth/callback", params={"code": "demo"})
    assert response.status_code == 302


def _tune(client: TestClient, memory_db: MemorySession) -> tuple[str, object]:
    _login(client)
    tenant = next(iter(memory_db.tenants.values()))
    tenant.min_guests = 1
    tenant.max_guests = 300
    tenant.waiter_cost_per_event = Decimal("0.00")
    tenant.default_tax_rate = 0.16
    tenant.show_prices_public = True
    tenant.has_active_plan = True
    tenant.whatsapp_phone = "+5213312345678"
    tenant.max_concurrent_events_per_slot = 1
    tenant.travel_buffer_minutes = 60
    slug = client.get("/api/auth/session").json()["slug"]
    return slug, tenant


def _package(
    client: TestClient, memory_db: MemorySession, *, name: str = "Taquiza"
) -> str:
    category = ServiceCategory(name=name, slug=f"{name.lower()}-qa", icon="")
    memory_db.add(category)
    created = client.post(
        "/api/v1/menu/packages",
        json={
            "category_id": str(category.id),
            "name": name,
            "base_price_per_guest": "100.00",
            "min_guests": 1,
        },
    )
    assert created.status_code == 201
    return str(created.json()["id"])


def _slot(client: TestClient, day: date) -> str:
    created = client.post(
        "/api/v1/schedule/slots",
        json={
            "day_of_week": day.weekday(),
            "start_time": "10:00",
            "end_time": "12:00",
            "is_active": True,
        },
    )
    assert created.status_code == 201
    assert created.json()["day_name"]
    return str(created.json()["id"])


def _quote_body(
    package_id: str, slot_id: str, day: date, **extra: object
) -> dict[str, object]:
    body: dict[str, object] = {
        "package_id": package_id,
        "event_date": day.isoformat(),
        "slot_id": slot_id,
        "guest_count": 2,
        "full_name": "Ana López",
        "phone": "+5213311111111",
        "whatsapp_phone": "+5213311111111",
        "email": "ana@example.com",
        "venue_address": "Av. México 10",
        "special_requests": "Sin picante",
    }
    body.update(extra)
    return body


def test_landing_quote_discount_iva_pdf_and_convert(
    client: TestClient, memory_db: MemorySession, monkeypatch: object
) -> None:
    from pytest import MonkeyPatch

    patch: MonkeyPatch = monkeypatch  # type: ignore[assignment]
    patch.setattr(settings, "IBISTRO_CONCIERGE_PHONE", "+5213300000000")
    patch.setattr(settings, "SMTP_HOST", "localhost")
    patch.setattr(settings, "EMAILS_FROM_EMAIL", "avisos@ibistro.mx")

    def fail_email(**_kwargs: object) -> None:
        raise RuntimeError("smtp")

    patch.setattr("app.services.quoting.send_email", fail_email)
    slug, tenant = _tune(client, memory_db)
    day = date.today() + timedelta(days=1)
    package_id = _package(client, memory_db)
    slot_id = _slot(client, day)
    photo = client.post(
        "/api/v1/schedule/photos",
        json={
            "image_url": "https://cdn.example/mesa.jpg",
            "caption": "Mesa de tacos",
            "display_order": 1,
        },
    )
    assert photo.status_code == 201
    zone = client.post(
        "/api/v1/schedule/zones",
        json={"zone_name": "Zapopan", "freight_cost": "50.00"},
    )
    assert zone.status_code == 201
    dashboard_slot = client.post(
        "/dashboard/quotes/slots",
        data={
            "day_of_week": str(day.weekday()),
            "start_time": "18:00",
            "end_time": "20:00",
            "is_active": "true",
        },
    )
    assert dashboard_slot.status_code == 200
    assert "Horarios de servicio" in dashboard_slot.text

    landing = client.get(f"/c/{slug}")
    assert landing.status_code == 200
    assert 'lang="es"' in landing.text
    assert "Catering Demo" in landing.text
    assert "Mesa de tacos" in landing.text
    assert "https://cdn.example/mesa.jpg" in landing.text
    assert f"provider_id:{tenant.id}" in landing.text  # type: ignore[attr-defined]
    assert 'hx-get="/api/v1/public/' in landing.text
    assert "Taquiza" in landing.text
    assert "$100.00" in landing.text

    slots = client.get(f"/api/v1/public/{slug}/slots", params={"date": day.isoformat()})
    assert slots.status_code == 200
    assert any(row["id"] == slot_id for row in slots.json())
    partial = client.get(
        f"/api/v1/public/{slug}/slots",
        params={"date": day.isoformat()},
        headers={"HX-Request": "true"},
    )
    assert "10:00" in partial.text
    assert "lugar" in partial.text

    body = _quote_body(package_id, slot_id, day, delivery_zone_id=zone.json()["id"])
    preview = client.post(
        f"/c/{slug}/preview", data={key: str(value) for key, value in body.items()}
    )
    assert preview.status_code == 200
    assert "$290.00" in preview.text

    created = client.post(f"/api/v1/public/{slug}/quotes", json=body)
    assert created.status_code == 201
    payload = created.json()
    assert payload["status"] == "PENDING_REVIEW"
    assert payload["message"] == "Cotización registrada"
    assert Decimal(payload["total_amount"]) == Decimal("290.00")
    assert "wa.me/5213300000000" in payload["tracking_url"]
    quote_id = payload["id"]

    desk = client.get("/dashboard/quotes")
    assert "Ana López" in desk.text
    assert "Descuento" in desk.text
    assert "IVA" in desk.text
    assert "Aprobar y Convertir a Reservación" in desk.text

    adjusted = client.post(
        f"/dashboard/quotes/{quote_id}/adjust",
        data={"discount_amount": "50", "apply_tax": "true", "tax_rate": "0.16"},
    )
    assert adjusted.status_code == 200
    assert "$232.00" in adjusted.text

    too_much = client.patch(
        f"/api/v1/quotes/{quote_id}",
        json={"discount_amount": "9999", "apply_tax": True},
    )
    assert too_much.status_code == 422

    without_tax = client.patch(
        f"/api/v1/quotes/{quote_id}",
        json={"discount_amount": "50", "apply_tax": False, "tax_rate": "0.16"},
    )
    assert without_tax.status_code == 200
    assert Decimal(without_tax.json()["tax_amount"]) == Decimal("0.00")
    assert Decimal(without_tax.json()["total_amount"]) == Decimal("200.00")

    pdf = client.get(f"/api/v1/quotes/{quote_id}/pdf")
    assert pdf.status_code == 200
    assert pdf.headers["content-type"].startswith("application/pdf")
    assert pdf.content.startswith(b"%PDF")
    dashboard_pdf = client.get(f"/dashboard/quotes/{quote_id}/pdf")
    assert dashboard_pdf.content.startswith(b"%PDF")

    converted = client.post(f"/api/v1/quotes/{quote_id}/convert")
    assert converted.status_code == 200
    assert converted.json()["status"] == "APPROVED"
    assert converted.json()["reservation_id"]
    again = client.post(f"/dashboard/quotes/{quote_id}/convert")
    assert again.status_code == 409
    assert "ya es una reservación" in again.text


def test_hidden_prices_inactive_plan_and_unknown_slug(
    client: TestClient, memory_db: MemorySession, monkeypatch: object
) -> None:
    from pytest import MonkeyPatch

    patch: MonkeyPatch = monkeypatch  # type: ignore[assignment]
    patch.setattr(settings, "IBISTRO_CONCIERGE_PHONE", "+5213300000000")
    slug, tenant = _tune(client, memory_db)
    tenant.show_prices_public = False  # type: ignore[attr-defined]
    day = date.today() + timedelta(days=1)
    package_id = _package(client, memory_db, name="Privado")
    slot_id = _slot(client, day)
    landing = client.get(f"/c/{slug}")
    assert landing.status_code == 200
    assert "Privado" in landing.text
    assert "$" not in landing.text
    profile = client.get(f"/api/v1/public/{slug}")
    assert profile.status_code == 200
    assert "base_price_per_guest" not in profile.json()["packages"][0]

    created = client.post(
        f"/api/v1/public/{slug}/quotes",
        json=_quote_body(package_id, slot_id, day),
    )
    assert created.status_code == 201
    assert created.json()["message"] == "Cotización lista para revisión personalizada"
    assert "total_amount" not in created.json()
    page = client.post(
        f"/c/{slug}/quotes",
        data={
            key: str(value)
            for key, value in _quote_body(package_id, slot_id, day).items()
        },
    )
    assert page.status_code == 201
    assert "Cotización lista para revisión personalizada" in page.text
    assert "$" not in page.text

    stored = client.get(f"/api/v1/quotes/{created.json()['id']}")
    assert Decimal(stored.json()["total_amount"]) == Decimal("232.00")

    tenant.has_active_plan = False  # type: ignore[attr-defined]
    paused = client.get(f"/c/{slug}")
    assert paused.status_code == 200
    assert "Proveedor no disponible temporalmente" in paused.text
    rejected = client.post(
        f"/api/v1/public/{slug}/quotes",
        json=_quote_body(package_id, slot_id, day),
    )
    assert rejected.status_code == 409
    assert rejected.json()["detail"] == "Proveedor no disponible temporalmente"
    missing = client.get("/c/no-existe")
    assert missing.status_code == 404
    assert "No se encontró el proveedor" in missing.text


def test_full_slot_rejects_a_public_quote(
    client: TestClient, memory_db: MemorySession
) -> None:
    slug, tenant = _tune(client, memory_db)
    day = date.today() + timedelta(days=1)
    package_id = _package(client, memory_db, name="Lleno")
    slot_id = _slot(client, day)
    memory_db.add(
        Reservation(
            tenant_id=tenant.id,  # type: ignore[attr-defined]
            customer_name="Ocupado",
            customer_phone="+5213311111111",
            venue_address="Calle 2",
            event_date=day,
            slot_id=UUID(slot_id),
            guest_count=10,
            total_amount=Decimal("10.00"),
            operation_status=OperationStatus.CONFIRMED,
        )
    )
    created = client.post(
        f"/api/v1/public/{slug}/quotes",
        json=_quote_body(package_id, slot_id, day),
    )
    assert created.status_code == 409
    assert created.json()["detail"] == "Ese horario ya no tiene lugar"


def test_convert_commits_stock_and_a_second_convert_conflicts(
    client: TestClient, memory_db: MemorySession
) -> None:
    slug, _tenant = _tune(client, memory_db)
    day = date.today() + timedelta(days=2)
    category = ServiceCategory(name="Stock", slug="stock-qa", icon="")
    memory_db.add(category)
    recipe = client.post(
        "/api/v1/menu/recipes",
        json={"name": "Pastor", "portion_size": 1, "portion_unit": "pz"},
    )
    ingredient = client.post(
        "/api/v1/warehouses/ingredients",
        json={
            "name": "Carne",
            "unit": "kg",
            "purchase_price": "10.00",
            "min_stock": 0,
            "max_stock": 20,
            "waste_factor": 0,
            "cooking_yield_factor": 1,
        },
    )
    assert recipe.status_code == 201
    client.post(
        f"/api/v1/menu/recipes/{recipe.json()['id']}/items",
        json={"ingredient_id": ingredient.json()["id"], "net_qty_per_portion": 1},
    )
    package = client.post(
        "/api/v1/menu/packages",
        json={
            "category_id": str(category.id),
            "name": "Pastor",
            "base_price_per_guest": "80.00",
            "min_guests": 1,
        },
    )
    grouped = client.post(
        f"/api/v1/menu/packages/{package.json()['id']}/groups",
        json={
            "group_name": "Guisos",
            "min_choices": 1,
            "max_choices": 1,
            "is_fixed": False,
        },
    )
    group_id = grouped.json()["groups"][0]["id"]
    client.post(
        f"/api/v1/menu/groups/{group_id}/options",
        json={"recipe_id": recipe.json()["id"], "portions_per_guest": 1},
    )
    asset = client.post(
        "/api/v1/equipment/assets",
        json={
            "name": "Chafer",
            "category": "Calentamiento",
            "total_stock": 4,
            "rental_price_per_unit": "0",
            "replacement_cost": "100",
        },
    )
    client.post(
        "/api/v1/equipment/rules",
        json={
            "package_id": package.json()["id"],
            "asset_id": asset.json()["id"],
            "guests_per_unit": 25,
        },
    )
    slot_id = _slot(client, day)
    created = client.post(
        f"/api/v1/public/{slug}/quotes",
        json=_quote_body(
            package.json()["id"],
            slot_id,
            day,
            selected_options={group_id: [recipe.json()["id"]]},
        ),
    )
    assert created.status_code == 201
    quote_id = created.json()["id"]

    blocked = client.post(f"/api/v1/quotes/{quote_id}/convert")
    assert blocked.status_code == 409
    assert "almacén primario" in blocked.json()["detail"]
    assert Reservation not in memory_db.rows or not any(
        row.quote_id is not None and str(row.quote_id) == quote_id
        for row in memory_db.rows.get(Reservation, {}).values()
    )

    warehouse = client.post(
        "/api/v1/warehouses",
        json={"name": "Central", "is_primary": True},
    )
    client.post(
        "/api/v1/warehouses/movements",
        json={
            "warehouse_id": warehouse.json()["id"],
            "ingredient_id": ingredient.json()["id"],
            "movement_type": "PURCHASE_IN",
            "quantity": 1,
        },
    )
    short = client.post(f"/api/v1/quotes/{quote_id}/convert")
    assert short.status_code == 409
    assert short.json()["detail"] == "No hay existencia disponible para reservar"
    assert not memory_db.rows.get(Reservation)

    client.post(
        "/api/v1/warehouses/movements",
        json={
            "warehouse_id": warehouse.json()["id"],
            "ingredient_id": ingredient.json()["id"],
            "movement_type": "PURCHASE_IN",
            "quantity": 5,
        },
    )
    converted = client.post(f"/api/v1/quotes/{quote_id}/convert")
    assert converted.status_code == 200
    stock = client.get("/api/v1/warehouses/stock")
    carne = next(row for row in stock.json() if row["ingredient_name"] == "Carne")
    assert carne["committed_stock"] == 2
    assert carne["physical_stock"] == 6
    again = client.post(f"/api/v1/quotes/{quote_id}/convert")
    assert again.status_code == 409


def test_quote_from_another_tenant_stays_hidden(
    client: TestClient, memory_db: MemorySession
) -> None:
    _tune(client, memory_db)
    foreign = Quote(
        tenant_id=uuid4(),
        lead_id=uuid4(),
        package_id=uuid4(),
        event_date=date.today(),
        slot_id=uuid4(),
        venue_address="Ajena",
        guest_count=10,
        waiters_count=1,
        subtotal=Decimal("10.00"),
        total_amount=Decimal("10.00"),
        estimated_cogs=Decimal("0.00"),
    )
    memory_db.add(foreign)
    listed = client.get("/api/v1/quotes")
    assert listed.status_code == 200
    assert str(foreign.id) not in [row["id"] for row in listed.json()]
    missing = client.get(f"/api/v1/quotes/{foreign.id}")
    assert missing.status_code == 404


def test_schedule_rejects_bad_hours_and_a_used_slot(
    client: TestClient, memory_db: MemorySession
) -> None:
    slug, tenant = _tune(client, memory_db)
    day = date.today() + timedelta(days=3)
    bad = client.post(
        "/api/v1/schedule/slots",
        json={
            "day_of_week": day.weekday(),
            "start_time": "18:00",
            "end_time": "10:00",
        },
    )
    assert bad.status_code == 422
    photo = client.post(
        "/api/v1/schedule/photos",
        json={"image_url": "nota-url", "caption": "Mala"},
    )
    assert photo.status_code == 422
    package_id = _package(client, memory_db, name="Agenda")
    slot_id = _slot(client, day)
    created = client.post(
        f"/api/v1/public/{slug}/quotes",
        json=_quote_body(package_id, slot_id, day),
    )
    assert created.status_code == 201
    removed = client.delete(f"/api/v1/schedule/slots/{slot_id}")
    assert removed.status_code == 409
    assert tenant is not None
    with pytest.raises(HTTPException):
        parse_clock("no")
    with pytest.raises(HTTPException):
        parse_day(9)


def test_validation_extras_equipment_and_desk_errors(
    client: TestClient, memory_db: MemorySession
) -> None:
    slug, tenant = _tune(client, memory_db)
    tenant.category_tags = ["BBQ"]  # type: ignore[attr-defined]
    tenant.max_concurrent_events_per_slot = 5  # type: ignore[attr-defined]
    day = date.today() + timedelta(days=4)
    package_id = _package(client, memory_db, name="Uno")
    category_id = client.get("/api/v1/menu/packages").json()[0]["category_id"]
    second = client.post(
        "/api/v1/menu/packages",
        json={
            "category_id": category_id,
            "name": "Dos",
            "base_price_per_guest": "90.00",
            "min_guests": 1,
        },
    )
    assert second.status_code == 201
    landing = client.get(f"/c/{slug}")
    assert "BBQ" in landing.text
    assert "Dos" in landing.text

    slot_id = _slot(client, day)
    listed = client.get("/api/v1/schedule/slots")
    assert listed.status_code == 200
    assert client.get("/api/v1/schedule/photos").status_code == 200
    assert client.get("/api/v1/schedule/zones").status_code == 200
    invalid_day = client.get(f"/api/v1/public/{slug}/slots", params={"date": "ayer"})
    assert invalid_day.status_code == 422

    recipe = client.post(
        "/api/v1/menu/recipes",
        json={"name": "Arroz", "portion_size": 1, "portion_unit": "pz"},
    )
    client.post(
        f"/api/v1/menu/packages/{package_id}/groups",
        json={
            "group_name": "Incluido",
            "min_choices": 1,
            "max_choices": 1,
            "is_fixed": True,
        },
    )
    choice = client.post(
        f"/api/v1/menu/packages/{package_id}/groups",
        json={
            "group_name": "Guiso",
            "min_choices": 1,
            "max_choices": 1,
            "is_fixed": False,
        },
    )
    groups = {group["group_name"]: group["id"] for group in choice.json()["groups"]}
    group_id = groups["Guiso"]
    client.post(
        f"/api/v1/menu/groups/{group_id}/options",
        json={"recipe_id": recipe.json()["id"]},
    )
    fixed_id = groups["Incluido"]
    client.post(
        f"/api/v1/menu/groups/{fixed_id}/options",
        json={"recipe_id": recipe.json()["id"]},
    )
    per_unit = client.post(
        "/api/v1/menu/extras",
        json={"name": "Agua", "unit_price": "10.00", "pricing_type": "PER_UNIT"},
    )
    per_guest = client.post(
        "/api/v1/menu/extras",
        json={"name": "Postre", "unit_price": "5.00", "pricing_type": "PER_GUEST"},
    )
    assert per_unit.status_code == 201
    body = _quote_body(
        package_id,
        slot_id,
        day,
        guest_count=2,
        selected_options={group_id: [recipe.json()["id"]]},
        extras=[
            {"extra_id": per_unit.json()["id"], "quantity": 2},
            {"extra_id": per_guest.json()["id"], "quantity": 1},
        ],
    )
    created = client.post(f"/api/v1/public/{slug}/quotes", json=body)
    assert created.status_code == 201, created.text
    # 200 de paquete + 20 de agua + 10 de postre, IVA 16% = 266.80
    assert Decimal(created.json()["total_amount"]) == Decimal("266.80")

    form = {
        key: str(value)
        for key, value in _quote_body(package_id, slot_id, day).items()
        if key != "selected_options"
    }
    form["choice"] = f"{group_id}:{recipe.json()['id']}"
    form["extra"] = per_unit.json()["id"]
    form[f"extra_qty_{per_unit.json()['id']}"] = "1"
    html_quote = client.post(f"/c/{slug}/quotes", data=form)
    assert html_quote.status_code == 201

    assert (
        client.post(f"/c/{slug}/quotes", data={"guest_count": "2"}).status_code == 422
    )
    assert (
        client.post(
            f"/c/{slug}/quotes",
            data={"package_id": package_id, "guest_count": "2"},
        ).status_code
        == 422
    )
    bad_choice = dict(form)
    bad_choice["choice"] = "sin-separador"
    assert client.post(f"/c/{slug}/quotes", data=bad_choice).status_code == 422
    empty_group = dict(form)
    empty_group["choice"] = f":{recipe.json()['id']}"
    assert client.post(f"/c/{slug}/quotes", data=empty_group).status_code == 422
    bad_date = dict(form)
    bad_date["event_date"] = "ayer"
    assert client.post(f"/c/{slug}/preview", data=bad_date).status_code == 422

    choices = {group_id: [recipe.json()["id"]]}
    tenant.min_guests = 8  # type: ignore[attr-defined]
    few = client.post(
        f"/api/v1/public/{slug}/quotes",
        json=_quote_body(package_id, slot_id, day, guest_count=2),
    )
    assert few.status_code == 422
    assert "mínimo" in few.json()["detail"]
    tenant.min_guests = 1  # type: ignore[attr-defined]
    tenant.max_guests = 3  # type: ignore[attr-defined]
    many = client.post(
        f"/api/v1/public/{slug}/quotes",
        json=_quote_body(package_id, slot_id, day, guest_count=4),
    )
    assert many.status_code == 422
    assert "máximo" in many.json()["detail"]
    tenant.max_guests = 300  # type: ignore[attr-defined]

    blank = _quote_body(package_id, slot_id, day, selected_options=choices)
    blank["phone"] = ""
    assert client.post(f"/api/v1/public/{slug}/quotes", json=blank).status_code == 422
    blank["phone"] = "+5213311111111"
    blank["venue_address"] = " "
    assert client.post(f"/api/v1/public/{slug}/quotes", json=blank).status_code == 422
    blank["venue_address"] = "Av. México 10"
    blank["delivery_zone_id"] = str(uuid4())
    assert client.post(f"/api/v1/public/{slug}/quotes", json=blank).status_code == 404

    paused = client.patch(
        f"/api/v1/menu/packages/{second.json()['id']}", json={"is_active": False}
    )
    assert paused.status_code == 200
    hidden = client.post(
        f"/api/v1/public/{slug}/quotes",
        json=_quote_body(second.json()["id"], slot_id, day),
    )
    assert hidden.status_code == 422
    assert (
        client.post(
            f"/api/v1/public/{slug}/quotes",
            json=_quote_body(str(uuid4()), slot_id, day),
        ).status_code
        == 404
    )

    quote_id = created.json()["id"]
    bad_rate = client.patch(
        f"/api/v1/quotes/{quote_id}",
        json={"discount_amount": "0", "apply_tax": True, "tax_rate": "2"},
    )
    assert bad_rate.status_code == 422
    stored = memory_db.rows[Quote][UUID(quote_id)]
    stored.selected_options_json = {"nope": [str(uuid4())], "bad": "x"}
    stored.selected_extras_json = {}
    stored.package_id = uuid4()
    stored.lead_id = uuid4()
    stored.slot_id = uuid4()
    detail = client.get(f"/api/v1/quotes/{quote_id}")
    assert detail.json()["package_name"] == "Paquete"
    assert detail.json()["lead_name"] == "Cliente"
    assert detail.json()["slot_label"] == ""
    stored.status = QuoteStatus.REJECTED
    rejected = client.post(f"/api/v1/quotes/{quote_id}/convert")
    assert rejected.status_code == 422

    plain = client.post(
        f"/api/v1/public/{slug}/quotes",
        json=_quote_body(package_id, slot_id, day, selected_options=choices),
    )
    assert plain.status_code == 201
    plain_row = memory_db.rows[Quote][UUID(plain.json()["id"])]
    plain_row.selected_equipment_json = {
        "lines": [
            "no",
            {
                "asset_id": str(uuid4()),
                "units": "1",
                "name": "Fantasma",
                "rental": "0.00",
            },
        ]
    }
    missing_asset = client.post(f"/api/v1/quotes/{plain.json()['id']}/convert")
    assert missing_asset.status_code == 404
    plain_row.selected_equipment_json = {"lines": []}
    plain_row.selected_options_json = {
        **plain_row.selected_options_json,
        "nope": [str(uuid4())],
        "bad": "x",
    }
    approved = client.post(f"/api/v1/quotes/{plain.json()['id']}/convert")
    assert approved.status_code == 200, approved.text
    locked = client.patch(
        f"/api/v1/quotes/{plain.json()['id']}",
        json={"discount_amount": "1", "apply_tax": True, "tax_rate": "2"},
    )
    assert locked.status_code == 409

    asset = client.post(
        "/api/v1/equipment/assets",
        json={
            "name": "Mantel",
            "category": "Manteleria",
            "total_stock": 2,
            "rental_price_per_unit": "0",
            "replacement_cost": "50",
        },
    )
    client.post(
        "/api/v1/equipment/rules",
        json={
            "package_id": package_id,
            "asset_id": asset.json()["id"],
            "guests_per_unit": 1,
        },
    )
    held = client.post(
        f"/api/v1/public/{slug}/quotes",
        json=_quote_body(
            package_id, slot_id, day, guest_count=2, selected_options=choices
        ),
    )
    assert held.status_code == 201
    assert client.post(f"/api/v1/quotes/{held.json()['id']}/convert").status_code == 200
    crowded = client.post(
        f"/api/v1/public/{slug}/quotes",
        json=_quote_body(
            package_id, slot_id, day, guest_count=2, selected_options=choices
        ),
    )
    assert crowded.status_code == 409
    assert crowded.json()["detail"] == "No hay equipo disponible para esa fecha"

    free_slot = client.post(
        "/api/v1/schedule/slots",
        json={
            "day_of_week": day.weekday(),
            "start_time": "15:00",
            "end_time": "16:00",
        },
    )
    assert (
        client.delete(f"/api/v1/schedule/slots/{free_slot.json()['id']}").status_code
        == 204
    )
    photo = client.post(
        "/api/v1/schedule/photos",
        json={"image_url": "https://cdn.example/foto.jpg", "display_order": 0},
    )
    assert (
        client.delete(f"/api/v1/schedule/photos/{photo.json()['id']}").status_code
        == 204
    )
    long_url = "https://cdn.example/" + ("a" * 2100)
    assert (
        client.post(
            "/api/v1/schedule/photos",
            json={"image_url": long_url, "display_order": -1},
        ).status_code
        == 422
    )
    only_reservation = client.post(
        "/api/v1/schedule/slots",
        json={
            "day_of_week": day.weekday(),
            "start_time": "16:00",
            "end_time": "17:00",
        },
    )
    memory_db.add(
        Reservation(
            tenant_id=tenant.id,  # type: ignore[attr-defined]
            customer_name="Mesa",
            customer_phone="+5213311111111",
            venue_address="Calle",
            event_date=day,
            slot_id=UUID(only_reservation.json()["id"]),
            guest_count=4,
            total_amount=Decimal("10.00"),
        )
    )
    assert (
        client.delete(
            f"/api/v1/schedule/slots/{only_reservation.json()['id']}"
        ).status_code
        == 409
    )

    desk_slot = client.post(
        "/dashboard/quotes/slots",
        data={
            "day_of_week": str(day.weekday()),
            "start_time": "18:00",
            "end_time": "10:00",
        },
    )
    assert desk_slot.status_code == 422
    assert "posterior" in desk_slot.text
    desk_photo = client.post(
        "/dashboard/quotes/photos",
        data={"image_url": "nota", "display_order": "0"},
    )
    assert desk_photo.status_code == 422
    desk_zone = client.post(
        "/dashboard/quotes/zones",
        data={"zone_name": "", "freight_cost": "10"},
    )
    assert desk_zone.status_code == 422
    bad_adjust = client.post(
        f"/dashboard/quotes/{plain.json()['id']}/adjust",
        data={"discount_amount": "no", "tax_rate": ""},
    )
    assert bad_adjust.status_code == 422

    tenant.waiter_ratio = 0  # type: ignore[attr-defined]
    tenant.waiter_cost_per_event = Decimal("10.00")  # type: ignore[attr-defined]
    waited = client.post(
        f"/api/v1/public/{slug}/quotes",
        json=_quote_body(second.json()["id"], slot_id, day, guest_count=2),
    )
    # The second package was deactivated, so this must fail closed.
    assert waited.status_code == 422
    client.patch(
        f"/api/v1/menu/packages/{second.json()['id']}", json={"is_active": True}
    )
    waited = client.post(
        f"/api/v1/public/{slug}/quotes",
        json=_quote_body(second.json()["id"], slot_id, day, guest_count=2),
    )
    assert waited.status_code == 201
    # 180 package + 2 meseros * 10, IVA 16%.
    assert Decimal(waited.json()["total_amount"]) == Decimal("232.00")


def test_pdf_prefers_weasyprint_and_falls_back(monkeypatch: pytest.MonkeyPatch) -> None:
    document = QuoteDocument(
        business_name="Casa",
        rfc="",
        address="",
        client_name="Ana",
        phone="+5213311111111",
        event_date="2026-11-23",
        slot_label="10:00–12:00",
        venue="Calle",
        guests="20",
        waiters="1",
        package_name="Taquiza",
        options=tuple((f"Grupo {index}", "Receta") for index in range(40)),
        extras=(("Agua", "10.00"),),
        equipment=(("Mantel x2", "0.00"),),
        package_price="200.00",
        waiter_cost="0.00",
        freight_name="",
        freight="0.00",
        subtotal="200.00",
        discount="0.00",
        tax="32.00",
        total="232.00",
        special_requests="",
        token="folio",
        status_label="En revisión",
    )

    class _Html:
        def __init__(self, string: str) -> None:
            self.string = string

        def write_pdf(self) -> bytes:
            return b"%PDF-weasy"

    module = types.ModuleType("weasyprint")
    module.HTML = _Html  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "weasyprint", module)
    assert render_quote_pdf(document).startswith(b"%PDF-weasy")

    def _broken(self: object) -> bytes:
        del self
        raise OSError("gtk")

    _Html.write_pdf = _broken  # type: ignore[method-assign]
    assert render_quote_pdf(document).startswith(b"%PDF")
    module.HTML = None  # type: ignore[attr-defined]
    assert render_quote_pdf(document).startswith(b"%PDF")

    class _Text:
        def __init__(self, string: str) -> None:
            del string

        def write_pdf(self) -> str:
            return "no"

    module.HTML = _Text  # type: ignore[attr-defined]
    assert render_quote_pdf(document).startswith(b"%PDF")
    assert _pesos("nope") == "nope"
