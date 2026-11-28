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
        "start_time": "10:00",
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
        "/api/v1/schedule/slots",
        json={
            "day_of_week": day.weekday(),
            "start_time": "18:00",
            "end_time": "20:00",
            "is_active": True,
        },
    )
    assert dashboard_slot.status_code == 201
    assert dashboard_slot.json()["start_time"] == "18:00"

    landing = client.get(f"/c/{slug}")
    assert landing.status_code == 200
    assert 'lang="es"' in landing.text
    assert "Catering Demo" in landing.text
    assert "Mesa de tacos" in landing.text
    assert "https://cdn.example/mesa.jpg" in landing.text
    assert f"provider_id:{tenant.id}" in landing.text  # type: ignore[attr-defined]
    assert f"/c/{slug}/availability" in landing.text
    assert "Taquiza" in landing.text
    assert "$100.00" in landing.text
    assert f'pickPackage("{package_id}", "Taquiza", "100.00")' in landing.text
    assert "Seleccionar servicio" in landing.text
    assert "Seleccionado ✓" in landing.text
    assert 'pickCategory("' in landing.text
    assert '", "Taquiza")' in landing.text

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

    desk = client.get("/api/v1/quotes")
    assert any(row["lead_name"] == "Ana López" for row in desk.json())
    adjusted = client.patch(
        f"/api/v1/quotes/{quote_id}",
        json={"discount_amount": "50", "apply_tax": True, "tax_rate": "0.16"},
    )
    assert adjusted.status_code == 200
    assert Decimal(adjusted.json()["total_amount"]) == Decimal("232.00")

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
    converted = client.post(f"/api/v1/quotes/{quote_id}/convert")
    assert converted.status_code == 200
    assert converted.json()["status"] == "APPROVED"
    assert converted.json()["reservation_id"]
    again = client.post(f"/api/v1/quotes/{quote_id}/convert")
    assert again.status_code == 409
    assert "ya es una reservación" in again.json()["detail"]


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

    converted = client.post(f"/api/v1/quotes/{quote_id}/convert")
    assert converted.status_code == 200
    assert any(
        row.quote_id is not None and str(row.quote_id) == quote_id
        for row in memory_db.rows.get(Reservation, {}).values()
    )

    later = day + timedelta(days=7)
    short_quote = client.post(
        f"/api/v1/public/{slug}/quotes",
        json=_quote_body(
            package.json()["id"],
            slot_id,
            later,
            selected_options={group_id: [recipe.json()["id"]]},
        ),
    )
    assert short_quote.status_code == 201
    short_id = short_quote.json()["id"]
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
    short = client.post(f"/api/v1/quotes/{short_id}/convert")
    assert short.status_code == 200
    assert any(
        row.quote_id is not None and str(row.quote_id) == short_id
        for row in memory_db.rows.get(Reservation, {}).values()
    )

    again = client.post(f"/api/v1/quotes/{quote_id}/convert")
    assert again.status_code == 409
    assert again.json()["detail"] == "Esta cotización ya es una reservación"


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
    assert "Folio" in html_quote.text
    assert "Enviar también por WhatsApp" in html_quote.text

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
    assert detail.json()["slot_label"] == "10:00–12:00"
    assert detail.json()["start_time"] == "10:00"
    assert detail.json()["end_time"] == "12:00"
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
        "/api/v1/schedule/slots",
        json={
            "day_of_week": day.weekday(),
            "start_time": "18:00",
            "end_time": "10:00",
        },
    )
    assert desk_slot.status_code == 422
    assert "posterior" in desk_slot.json()["detail"]
    desk_photo = client.post(
        "/api/v1/schedule/photos",
        json={"image_url": "nota", "display_order": 0},
    )
    assert desk_photo.status_code == 422
    desk_zone = client.post(
        "/api/v1/schedule/zones",
        json={"zone_name": "", "freight_cost": "10"},
    )
    assert desk_zone.status_code == 422
    bad_adjust = client.patch(
        f"/api/v1/quotes/{plain.json()['id']}",
        json={"discount_amount": "no", "tax_rate": ""},
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


def test_month_availability_and_extra_categories(
    client: TestClient, memory_db: MemorySession
) -> None:
    slug, _tenant = _tune(client, memory_db)
    day = date.today() + timedelta(days=1)
    slot_id = _slot(client, day)
    taquiza = ServiceCategory(name="Taquiza", slug="taquiza-mes", icon="🌮")
    italiana = ServiceCategory(name="Italiana", slug="italiana-mes", icon="")
    memory_db.add(taquiza)
    memory_db.add(italiana)
    created = client.post(
        "/api/v1/menu/packages",
        json={
            "category_id": str(taquiza.id),
            "name": "Taquiza",
            "base_price_per_guest": "100.00",
            "min_guests": 1,
        },
    )
    assert created.status_code == 201
    linked = client.post(
        "/api/v1/menu/extras",
        json={
            "name": "Arroz",
            "unit_price": "15.00",
            "pricing_type": "PER_UNIT",
            "category_ids": [str(taquiza.id)],
        },
    )
    assert linked.status_code == 201, linked.text
    assert linked.json()["category_ids"] == [str(taquiza.id)]
    assert linked.json()["category_names"] == ["Taquiza"]
    kept = client.patch(
        f"/api/v1/menu/extras/{linked.json()['id']}",
        json={"is_active": True},
    )
    assert kept.status_code == 200
    assert kept.json()["category_ids"] == [str(taquiza.id)]
    cleared = client.patch(
        f"/api/v1/menu/extras/{linked.json()['id']}",
        json={"category_ids": []},
    )
    assert cleared.status_code == 200
    assert cleared.json()["category_ids"] == []
    restored = client.patch(
        f"/api/v1/menu/extras/{linked.json()['id']}",
        json={"category_ids": [str(taquiza.id), str(taquiza.id)]},
    )
    assert restored.status_code == 200
    assert restored.json()["category_ids"] == [str(taquiza.id)]
    unknown = client.post(
        "/api/v1/menu/extras",
        json={
            "name": "Salsa",
            "unit_price": "5.00",
            "pricing_type": "PER_UNIT",
            "category_ids": [str(uuid4())],
        },
    )
    assert unknown.status_code == 422

    month = f"{day.year:04d}-{day.month:02d}"
    availability = client.get(f"/c/{slug}/availability", params={"month": month})
    assert availability.status_code == 200, availability.text
    body = availability.json()
    assert body["service_duration_minutes"] == 120
    found = next(item for item in body["days"] if item["date"] == day.isoformat())
    assert found["status"] == "available"
    assert found["available_slots"] == ["10:00"]
    assert found["bookings"][0]["slot_id"] == slot_id
    other = next(
        item
        for item in body["days"]
        if item["date"] >= date.today().isoformat()
        and date.fromisoformat(item["date"]).weekday() != day.weekday()
    )
    assert other["status"] == "closed"
    assert other["available_slots"] == []
    invalid = client.get(f"/c/{slug}/availability", params={"month": "2026-13"})
    assert invalid.status_code == 422
    assert "válido" in invalid.json()["detail"]

    profile = client.get(f"/api/v1/public/{slug}")
    assert profile.status_code == 200
    extras = {row["name"]: row for row in profile.json()["extras"]}
    assert extras["Arroz"]["category_ids"] == [str(taquiza.id)]
    landing = client.get(f"/c/{slug}")
    assert landing.status_code == 200
    assert "Fecha y hora del evento" in landing.text
    assert "Enviar Solicitud de Cotización" in landing.text
    assert "Arroz" in landing.text
    assert str(italiana.id) not in extras["Arroz"]["category_ids"]


def test_exact_schedule_rebook_and_closed_reservation(
    client: TestClient, memory_db: MemorySession
) -> None:
    slug, _tenant = _tune(client, memory_db)
    day = date.today() + timedelta(days=2)
    package_id = _package(client, memory_db)
    slot_id = _slot(client, day)

    missing = client.post(
        f"/api/v1/public/{slug}/quotes",
        json=_quote_body(package_id, slot_id, day, start_time=None),
    )
    assert missing.status_code == 422
    assert missing.json()["detail"] == "Elige una hora"

    created = client.post(
        f"/api/v1/public/{slug}/quotes",
        json=_quote_body(package_id, slot_id, day),
    )
    assert created.status_code == 201, created.text
    quote_id = created.json()["id"]
    detail = client.get(f"/api/v1/quotes/{quote_id}")
    assert detail.status_code == 200
    assert detail.json()["start_time"] == "10:00"
    assert detail.json()["end_time"] == "12:00"
    assert detail.json()["slot_label"] == "10:00–12:00"
    assert detail.json()["reservation_id"] is None
    assert detail.json()["can_rebook"] is False

    listed = client.get("/api/v1/quotes")
    row = next(item for item in listed.json() if item["id"] == quote_id)
    assert row["start_time"] == "10:00"
    assert row["end_time"] == "12:00"

    choice = {
        "event_date": day.isoformat(),
        "slot_id": slot_id,
        "start_time": "10:00",
    }
    moved = client.patch(f"/api/v1/quotes/{quote_id}/schedule", json=choice)
    assert moved.status_code == 200
    assert moved.json()["start_time"] == "10:00"
    assert moved.json()["end_time"] == "12:00"

    converted = client.post(f"/api/v1/quotes/{quote_id}/convert")
    assert converted.status_code == 200, converted.text
    reservation_id = converted.json()["reservation_id"]
    card = client.get(f"/api/v1/reservations/{reservation_id}")
    assert card.status_code == 200
    body = card.json()
    assert body["start_time"] == "10:00"
    assert body["end_time"] == "12:00"
    assert body["folio"]
    assert body["email"] == "ana@example.com"
    assert "wa.me/5213311111111" in body["whatsapp_url"]
    assert "+" not in body["whatsapp_url"].split("wa.me/", 1)[1].split("?", 1)[0]

    later = day + timedelta(days=7)
    later_choice = {
        "event_date": later.isoformat(),
        "slot_id": slot_id,
        "start_time": "10:00",
    }
    shifted = client.patch(f"/api/v1/reservations/{reservation_id}", json=later_choice)
    assert shifted.status_code == 200, shifted.text
    assert shifted.json()["start_time"] == "10:00"
    assert str(shifted.json()["event_date"]).startswith(later.isoformat())
    quote = client.get(f"/api/v1/quotes/{quote_id}")
    assert str(quote.json()["event_date"]).startswith(later.isoformat())

    closed = client.post(f"/api/v1/reservations/{reservation_id}/close")
    assert closed.status_code == 200, closed.text
    blocked = client.patch(f"/api/v1/reservations/{reservation_id}", json=later_choice)
    assert blocked.status_code == 403
    receipt = client.post(
        f"/api/v1/reservations/{reservation_id}/receipts",
        json={"amount": "10.00", "payment_method": "CASH"},
    )
    assert receipt.status_code == 403

    quote = client.get(f"/api/v1/quotes/{quote_id}")
    assert quote.json()["can_rebook"] is True
    assert quote.json()["reservation_id"] is None
    occupied = client.post(f"/api/v1/quotes/{quote_id}/convert", json=later_choice)
    assert occupied.status_code == 409

    free_day = later + timedelta(days=7)
    free_choice = {
        "event_date": free_day.isoformat(),
        "slot_id": slot_id,
        "start_time": "10:00",
    }
    again = client.post(f"/api/v1/quotes/{quote_id}/convert", json=free_choice)
    assert again.status_code == 200, again.text
    second_id = again.json()["reservation_id"]
    assert second_id != reservation_id
    duplicate = client.post(f"/api/v1/quotes/{quote_id}/convert", json=free_choice)
    assert duplicate.status_code == 409

    cancelled = client.post(f"/api/v1/reservations/{second_id}/cancel")
    assert cancelled.status_code == 200
    openings = client.get(
        "/api/v1/schedule/openings",
        params={"date": free_day.isoformat()},
    )
    assert openings.status_code == 200
    assert any(item["start_time"] == "10:00" for item in openings.json())
    rebooked = client.post(f"/api/v1/quotes/{quote_id}/convert", json=free_choice)
    assert rebooked.status_code == 200, rebooked.text
    assert rebooked.json()["reservation_id"] != second_id


def test_approve_quote_from_the_list(
    client: TestClient, memory_db: MemorySession
) -> None:
    _tune(client, memory_db)
    day = date.today() + timedelta(days=2)
    package_id = _package(client, memory_db)
    slot_id = _slot(client, day)
    created = client.post("/api/v1/quotes", json=_quote_body(package_id, slot_id, day))
    assert created.status_code == 201, created.text
    quote_id = created.json()["id"]
    approved = client.post(f"/api/v1/quotes/{quote_id}/approve")
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "APPROVED"
    assert approved.json()["status_label"] == "Aprobada"
    assert approved.json()["reservation_id"] is None
    again = client.post(f"/api/v1/quotes/{quote_id}/approve")
    assert again.status_code == 200
    stored = next(iter(memory_db.rows[Quote].values()))
    stored.status = QuoteStatus.REJECTED
    rejected = client.post(f"/api/v1/quotes/{quote_id}/approve")
    assert rejected.status_code == 422
    assert rejected.json()["detail"] == "La cotización está rechazada"


def test_dashboard_pos_creates_a_quote(
    client: TestClient, memory_db: MemorySession
) -> None:
    _tune(client, memory_db)
    day = date.today() + timedelta(days=3)
    package_id = _package(client, memory_db)
    slot_id = _slot(client, day)
    missing = client.post(
        "/api/v1/quotes",
        json=_quote_body(package_id, slot_id, day, start_time=None),
    )
    assert missing.status_code == 422
    assert missing.json()["detail"] == "Elige una hora"
    created = client.post(
        "/api/v1/quotes",
        json=_quote_body(package_id, slot_id, day),
    )
    assert created.status_code == 201, created.text
    assert created.json()["start_time"] == "10:00"
    assert created.json()["end_time"] == "12:00"
    assert created.json()["lead_name"] == "Ana López"


def test_quote_service_edit_and_reservation_log(
    client: TestClient, memory_db: MemorySession
) -> None:
    _tune(client, memory_db)
    day = date.today() + timedelta(days=4)
    package_id = _package(client, memory_db)
    slot_id = _slot(client, day)
    created = client.post(
        f"/api/v1/public/{client.get('/api/auth/session').json()['slug']}/quotes",
        json=_quote_body(package_id, slot_id, day),
    )
    assert created.status_code == 201, created.text
    quote_id = created.json()["id"]
    detail = client.get(f"/api/v1/quotes/{quote_id}")
    assert detail.status_code == 200
    body = detail.json()
    assert body["folio"]
    assert body["package_id"] == package_id
    assert body["variants"] == []
    edited = client.patch(
        f"/api/v1/quotes/{quote_id}",
        json={"guest_count": 4, "manual_total": "250.00"},
    )
    assert edited.status_code == 200, edited.text
    assert edited.json()["guest_count"] == 4
    assert edited.json()["total_amount"] == "250.00"
    converted = client.post(f"/api/v1/quotes/{quote_id}/convert")
    assert converted.status_code == 200, converted.text
    reservation_id = converted.json()["reservation_id"]
    blocked = client.patch(
        f"/api/v1/quotes/{quote_id}",
        json={"guest_count": 5},
    )
    assert blocked.status_code == 409
    changed = client.patch(
        f"/api/v1/reservations/{reservation_id}",
        json={
            "guest_count": 6,
            "event_date": day.isoformat(),
            "slot_id": slot_id,
            "start_time": "10:00",
            "manual_total": "300.00",
            "reason": "Más invitados",
        },
    )
    assert changed.status_code == 200, changed.text
    saved = changed.json()
    assert saved["guest_count"] == 6
    assert saved["total_amount"] == "300.00"
    assert saved["paid_amount"] == "0.00"
    assert saved["change_log"][-1]["reason"] == "Más invitados"
    assert saved["change_log"][-1]["before"]["guest_count"] == "4"
    assert saved["change_log"][-1]["after"]["guest_count"] == "6"
    closed = client.post(f"/api/v1/reservations/{reservation_id}/close")
    assert closed.status_code == 200, closed.text
    forbidden = client.patch(
        f"/api/v1/reservations/{reservation_id}",
        json={"guest_count": 7, "manual_total": "10.00"},
    )
    assert forbidden.status_code == 403
