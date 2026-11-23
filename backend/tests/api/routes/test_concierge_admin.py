"""Orion concierge API and the Nuna superuser desk."""

import asyncio
import json
from datetime import date, time, timedelta
from uuid import uuid4

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.security import encrypt_session
from app.models import (
    Ingredient,
    Lead,
    LeadSource,
    PlatformAuditLog,
    Quote,
    QuoteStatus,
    Recipe,
    ServiceCategory,
    ServiceScheduleSlot,
    Tenant,
)
from app.seed import seed
from app.services.catalog_clone import clone_master_catalog
from app.services.concierge import search_providers
from tests.memory_db import MemorySession

_TOKEN = "orion-test"


def _orion(monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    monkeypatch.setattr(settings, "ORION_SERVICE_TOKEN", _TOKEN)
    return {"X-API-Key": _TOKEN}


def _login(client: TestClient, code: str = "demo") -> None:
    response = client.get("/api/auth/callback", params={"code": code})
    assert response.status_code == 302


def _tenant(memory_db: MemorySession, org_id: str) -> Tenant:
    tenant = memory_db.tenants[org_id]
    return tenant


def _event() -> date:
    return date.today() + timedelta(days=1)


def _provider(
    memory_db: MemorySession,
    *,
    org_id: str,
    slug: str,
    name: str,
    score: int,
    event: date,
    verified: bool = True,
    plan: bool = True,
    tags: list[str] | None = None,
    min_guests: int = 20,
    max_guests: int = 300,
    with_slot: bool = True,
) -> Tenant:
    tenant = Tenant(
        nuna_org_id=org_id,
        slug=slug,
        business_name=name,
        category_tags=["taquiza"] if tags is None else tags,
        min_guests=min_guests,
        max_guests=max_guests,
        has_active_plan=plan,
        is_verified_concierge=verified,
        concierge_priority_score=score,
    )
    memory_db.add(tenant)
    if with_slot:
        memory_db.add(
            ServiceScheduleSlot(
                tenant_id=tenant.id,
                day_of_week=event.weekday(),
                start_time=time(10, 0),
                end_time=time(12, 0),
                is_active=True,
            )
        )
    return tenant


def test_orion_key_rejects_a_missing_service(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "ORION_SERVICE_TOKEN", "")
    missing = client.get("/api/v1/concierge/categories")
    assert missing.status_code == 503
    assert missing.json()["detail"] == "La llave de Orion no está configurada"

    monkeypatch.setattr(settings, "ORION_SERVICE_TOKEN", _TOKEN)
    absent = client.get("/api/v1/concierge/categories")
    wrong = client.get("/api/v1/concierge/categories", headers={"X-API-Key": "nope"})
    short = client.get("/api/v1/concierge/categories", headers={"X-API-Key": "x"})
    assert absent.status_code == 401
    assert wrong.status_code == 401
    assert short.status_code == 401
    assert absent.json()["detail"] == "La llave de Orion no es válida"


def test_search_returns_the_top_three_verified_providers(
    client: TestClient, memory_db: MemorySession, monkeypatch: pytest.MonkeyPatch
) -> None:
    headers = _orion(monkeypatch)
    event = _event()
    memory_db.add(ServiceCategory(name="Taquiza", slug="taquiza", icon="taco"))
    memory_db.add(
        ServiceCategory(name="Cerrada", slug="cerrada", icon="", is_active=False)
    )
    listed = client.get("/api/v1/concierge/categories", headers=headers)
    assert listed.status_code == 200
    assert [row["slug"] for row in listed.json()] == ["taquiza"]
    scored = [
        _provider(
            memory_db,
            org_id=f"org-{score}",
            slug=f"casa-{score}",
            name=f"Casa {score}",
            score=score,
            event=event,
            tags=["Taquiza"] if score == 400 else None,
        )
        for score in (100, 200, 300, 400)
    ]
    _provider(
        memory_db,
        org_id="org-empty",
        slug="sin-lugar",
        name="Sin lugar",
        score=900,
        event=event,
        with_slot=False,
    )
    _provider(
        memory_db,
        org_id="org-plain",
        slug="sin-verificar",
        name="Sin verificar",
        score=800,
        event=event,
        verified=False,
    )
    _provider(
        memory_db,
        org_id="org-paused",
        slug="sin-plan",
        name="Sin plan",
        score=700,
        event=event,
        plan=False,
    )
    _provider(
        memory_db,
        org_id="org-other",
        slug="otra-cocina",
        name="Otra cocina",
        score=600,
        event=event,
        tags=["sushi"],
    )
    _provider(
        memory_db,
        org_id="org-small",
        slug="mesa-chica",
        name="Mesa chica",
        score=550,
        event=event,
        max_guests=10,
    )
    _provider(
        memory_db,
        org_id="master-catalog",
        slug="catalogo-maestro",
        name="Catálogo maestro",
        score=1000,
        event=event,
    )
    found = client.get(
        "/api/v1/concierge/providers/search",
        headers=headers,
        params={
            "category_slug": "taquiza",
            "guest_count": 40,
            "event_date": event.isoformat(),
        },
    )
    assert found.status_code == 200
    body = found.json()
    assert [row["slug"] for row in body] == ["casa-400", "casa-300", "casa-200"]
    assert body[0]["concierge_priority_score"] == 400
    assert f"/c/{scored[3].slug}" in body[0]["landing_url"]
    assert f"event_date={event.isoformat()}" in body[0]["landing_url"]
    assert "guest_count=40" in body[0]["landing_url"]
    assert "category=taquiza" in body[0]["landing_url"]
    assert body[0]["slots"]

    unknown = client.get(
        "/api/v1/concierge/providers/search",
        headers=headers,
        params={
            "category_slug": "no-existe",
            "guest_count": 40,
            "event_date": event.isoformat(),
        },
    )
    assert unknown.status_code == 404
    closed = client.get(
        "/api/v1/concierge/providers/search",
        headers=headers,
        params={
            "category_slug": "cerrada",
            "guest_count": 40,
            "event_date": event.isoformat(),
        },
    )
    assert closed.status_code == 404
    zero = client.get(
        "/api/v1/concierge/providers/search",
        headers=headers,
        params={
            "category_slug": "taquiza",
            "guest_count": 0,
            "event_date": event.isoformat(),
        },
    )
    assert zero.status_code == 422
    with pytest.raises(HTTPException) as raised:
        asyncio.run(
            search_providers(
                memory_db,  # type: ignore[arg-type]
                category_slug="taquiza",
                guest_count=0,
                event_date=event,
            )
        )
    assert raised.value.status_code == 422


def test_menu_availability_and_both_quote_sources(
    client: TestClient, memory_db: MemorySession, monkeypatch: pytest.MonkeyPatch
) -> None:
    headers = _orion(monkeypatch)
    monkeypatch.setattr("app.services.quoting.send_email", lambda *args, **kwargs: None)
    _login(client)
    tenant = _tenant(memory_db, "mock-org")
    tenant.min_guests = 1
    tenant.show_prices_public = False
    event = _event()
    category = ServiceCategory(name="Taquiza", slug="taquiza-menu", icon="")
    memory_db.add(category)
    created = client.post(
        "/api/v1/menu/packages",
        json={
            "category_id": str(category.id),
            "name": "Taquiza",
            "base_price_per_guest": "100.00",
            "min_guests": 1,
        },
    )
    assert created.status_code == 201
    package_id = created.json()["id"]
    slot = client.post(
        "/api/v1/schedule/slots",
        json={
            "day_of_week": event.weekday(),
            "start_time": "10:00",
            "end_time": "12:00",
            "is_active": True,
        },
    )
    assert slot.status_code == 201

    hidden = client.get(
        f"/api/v1/concierge/providers/{tenant.id}/menu", headers=headers
    )
    assert hidden.status_code == 200
    assert hidden.json()["show_prices"] is False
    assert "base_price_per_guest" not in hidden.json()["packages"][0]

    tenant.show_prices_public = True
    shown = client.get(f"/api/v1/concierge/providers/{tenant.id}/menu", headers=headers)
    assert shown.json()["packages"][0]["base_price_per_guest"] == "100.00"

    open_days = client.get(
        f"/api/v1/concierge/providers/{tenant.id}/availability", headers=headers
    )
    assert open_days.status_code == 200
    assert any(day["slots"] for day in open_days.json()["days"])
    tenant.has_active_plan = False
    closed = client.get(
        f"/api/v1/concierge/providers/{tenant.id}/availability", headers=headers
    )
    assert closed.status_code == 200
    assert closed.json()["days"] == []
    assert closed.json()["business_name"] == tenant.business_name

    missing = client.get(
        f"/api/v1/concierge/providers/{uuid4()}/availability", headers=headers
    )
    assert missing.status_code == 404
    missing_menu = client.get(
        f"/api/v1/concierge/providers/{uuid4()}/menu", headers=headers
    )
    assert missing_menu.status_code == 404

    tenant.has_active_plan = True
    for source in ("whatsapp_direct", "whatsapp_concierge"):
        quoted = client.post(
            "/api/v1/concierge/quotes",
            headers=headers,
            json={
                "provider_id": str(tenant.id),
                "source": source,
                "package_id": package_id,
                "event_date": event.isoformat(),
                "slot_id": slot.json()["id"],
                "guest_count": 2,
                "full_name": "Ana López",
                "phone": "+5213311111111",
                "whatsapp_phone": "+5213311111111",
                "email": "ana@example.com",
                "venue_address": "Av. México 10",
            },
        )
        assert quoted.status_code == 200
        assert quoted.json()["status"] == QuoteStatus.PENDING_REVIEW
    leads = list(memory_db.rows[Lead].values())
    assert {row.source for row in leads} == {
        LeadSource.WHATSAPP_DIRECT,
        LeadSource.WHATSAPP_CONCIERGE,
    }
    assert all(
        row.status == QuoteStatus.PENDING_REVIEW
        for row in memory_db.rows[Quote].values()
    )

    rejected = client.post(
        "/api/v1/concierge/quotes",
        headers=headers,
        json={
            "provider_id": str(tenant.id),
            "source": "micro_landing",
            "package_id": package_id,
            "event_date": event.isoformat(),
            "slot_id": slot.json()["id"],
            "guest_count": 2,
            "full_name": "Ana López",
            "phone": "+5213311111111",
            "whatsapp_phone": "+5213311111111",
            "venue_address": "Av. México 10",
        },
    )
    assert rejected.status_code == 422
    tenant.has_active_plan = False
    paused = client.post(
        "/api/v1/concierge/quotes",
        headers=headers,
        json={
            "provider_id": str(tenant.id),
            "source": "whatsapp_direct",
            "package_id": package_id,
            "event_date": event.isoformat(),
            "slot_id": slot.json()["id"],
            "guest_count": 2,
            "full_name": "Ana López",
            "phone": "+5213311111111",
            "whatsapp_phone": "+5213311111111",
            "venue_address": "Av. México 10",
        },
    )
    assert paused.status_code == 409


def test_admin_impersonation_and_catalog_clone(
    client: TestClient, memory_db: MemorySession
) -> None:
    asyncio.run(seed())
    denied = client.get("/admin")
    assert denied.status_code == 401
    _login(client, "demo")
    forbidden = client.get("/admin")
    assert forbidden.status_code == 403
    demo = _tenant(memory_db, "mock-org")
    _login(client, "admin")
    page = client.get("/admin")
    assert page.status_code == 200
    assert "Categorías" in page.text
    assert "Catálogo maestro" not in page.text
    assert "Catering Demo" in page.text
    assert "Activo" in page.text

    created = client.post(
        "/admin/categories",
        data={"name": "Parrillada", "icon": "fire", "is_active": "on"},
    )
    assert created.status_code == 200
    assert "Parrillada" in created.text
    duplicate = client.post(
        "/admin/categories",
        data={"name": "Parrillada", "icon": "fire", "is_active": "on"},
    )
    assert duplicate.status_code == 409
    assert "Esa categoría ya existe" in duplicate.text
    blank = client.post("/admin/categories", data={"name": "  ", "icon": ""})
    assert blank.status_code == 422
    category = next(
        row for row in memory_db.categories.values() if row.name == "Parrillada"
    )
    renamed = client.post(
        f"/admin/categories/{category.id}",
        data={"name": "Parrilla", "icon": "grill", "is_active": "on"},
    )
    assert renamed.status_code == 200
    assert category.name == "Parrilla"
    missing_category = client.post(
        f"/admin/categories/{uuid4()}",
        data={"name": "Nadie", "icon": "", "is_active": "on"},
    )
    assert missing_category.status_code == 404

    saved = client.post(
        f"/admin/tenants/{demo.id}",
        data={
            "is_verified_concierge": "on",
            "concierge_priority_score": "250",
            "module": "catering_core",
        },
    )
    assert saved.status_code == 200
    assert demo.is_verified_concierge is True
    assert demo.concierge_priority_score == 250
    assert demo.enabled_modules == ["catering_core"]
    negative = client.post(
        f"/admin/tenants/{demo.id}",
        data={"concierge_priority_score": "-1"},
    )
    assert negative.status_code == 422
    assert "negativa" in negative.text
    unknown_module = client.post(
        f"/admin/tenants/{demo.id}",
        data={"concierge_priority_score": "10", "module": "nope"},
    )
    assert unknown_module.status_code == 422

    entered = client.post(f"/admin/impersonate/{demo.id}")
    assert entered.status_code == 302
    assert entered.headers["location"] == "/dashboard/menu"
    session = client.get("/api/auth/session")
    assert session.json()["slug"] == demo.slug
    desk = client.get("/dashboard/menu")
    assert "Viendo la cuenta de" in desk.text
    assert "Catering Demo" in desk.text
    audits = list(memory_db.rows[PlatformAuditLog].values())
    assert any(
        row.action == "impersonate" and row.target_tenant_id == demo.id
        for row in audits
    )

    cloned = client.post(f"/admin/tenants/{demo.id}/clone-templates")
    assert cloned.status_code == 200
    names = {
        row.name
        for row in memory_db.rows[Ingredient].values()
        if row.tenant_id == demo.id
    }
    assert names == {"Arroz", "Pollo"}
    recipes = [
        row
        for row in memory_db.rows[Recipe].values()
        if row.tenant_id == demo.id and row.name == "Arroz con pollo"
    ]
    assert len(recipes) == 1
    again = client.post(f"/admin/tenants/{demo.id}/clone-templates")
    assert again.status_code == 200
    assert (
        len(
            [
                row
                for row in memory_db.rows[Ingredient].values()
                if row.tenant_id == demo.id
            ]
        )
        == 2
    )

    stopped = client.post("/admin/impersonate/stop")
    assert stopped.status_code == 302
    assert "Viendo la cuenta de" not in client.get("/dashboard/menu").text
    assert any(
        row.action == "stop_impersonation"
        for row in memory_db.rows[PlatformAuditLog].values()
    )
    assert client.get("/api/auth/session").json()["slug"] != demo.slug

    missing_provider = client.post(f"/admin/impersonate/{uuid4()}")
    assert missing_provider.status_code == 404
    master = _tenant(memory_db, "master-catalog")
    with pytest.raises(HTTPException) as raised:
        asyncio.run(clone_master_catalog(memory_db, master.id))  # type: ignore[arg-type]
    assert raised.value.status_code == 422
    memory_db.tenants.pop("master-catalog", None)
    with pytest.raises(HTTPException) as missing_master:
        asyncio.run(clone_master_catalog(memory_db, demo.id))  # type: ignore[arg-type]
    assert missing_master.value.status_code == 404


def test_impersonation_cookie_is_ignored_when_it_is_not_the_actor(
    client: TestClient, memory_db: MemorySession
) -> None:
    _login(client, "demo")
    demo = _tenant(memory_db, "mock-org")
    other = Tenant(
        nuna_org_id="otra-org",
        slug="otra-casa",
        business_name="Otra casa",
        has_active_plan=True,
    )
    memory_db.add(other)
    client.cookies.set(
        "ibistro_impersonation",
        encrypt_session(
            json.dumps(
                {
                    "actor": "mock-org",
                    "tenant_id": str(other.id),
                    "business_name": "Otra casa",
                    "exp": "2099-01-01T00:00:00+00:00",
                }
            )
        ),
    )
    assert client.get("/api/auth/session").json()["slug"] == demo.slug
    assert "Viendo la cuenta de" not in client.get("/dashboard/menu").text

    _login(client, "admin")
    expired = encrypt_session(
        json.dumps(
            {
                "actor": "platform-admin",
                "tenant_id": str(demo.id),
                "business_name": "Catering Demo",
                "exp": "2000-01-01T00:00:00+00:00",
            }
        )
    )
    client.cookies.set("ibistro_impersonation", expired)
    admin = _tenant(memory_db, "platform-admin")
    assert client.get("/api/auth/session").json()["slug"] == admin.slug

    naive = encrypt_session(
        json.dumps(
            {
                "actor": "platform-admin",
                "tenant_id": str(demo.id),
                "business_name": "  ",
                "exp": "2099-01-01T00:00:00",
            }
        )
    )
    client.cookies.set("ibistro_impersonation", naive)
    assert client.get("/api/auth/session").json()["slug"] == demo.slug
    desk = client.get("/dashboard/menu")
    assert "Viendo la cuenta de el proveedor" in desk.text

    client.cookies.set("ibistro_impersonation", "no-es-una-cookie")
    assert client.get("/api/auth/session").json()["slug"] == admin.slug
    client.cookies.set(
        "ibistro_impersonation",
        encrypt_session(json.dumps(["no-es-un-objeto"])),
    )
    assert client.get("/api/auth/session").json()["slug"] == admin.slug
    client.cookies.set(
        "ibistro_impersonation",
        encrypt_session(
            json.dumps(
                {
                    "actor": "platform-admin",
                    "tenant_id": "no-uuid",
                    "business_name": "Nadie",
                    "exp": "2099-01-01T00:00:00+00:00",
                }
            )
        ),
    )
    assert client.get("/api/auth/session").json()["slug"] == admin.slug
    client.cookies.set(
        "ibistro_impersonation",
        encrypt_session(
            json.dumps(
                {
                    "actor": "otra-persona",
                    "tenant_id": str(demo.id),
                    "business_name": "Catering Demo",
                    "exp": "2099-01-01T00:00:00+00:00",
                }
            )
        ),
    )
    assert client.get("/api/auth/session").json()["slug"] == admin.slug
    client.cookies.set(
        "ibistro_impersonation",
        encrypt_session(json.dumps({"actor": "platform-admin", "exp": "mañana"})),
    )
    assert client.get("/api/auth/session").json()["slug"] == admin.slug
