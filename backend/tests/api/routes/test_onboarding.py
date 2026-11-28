from __future__ import annotations

from fastapi.testclient import TestClient
from pytest import MonkeyPatch
from sqlmodel import select

from app.models import Tenant, Warehouse
from tests.memory_db import MemorySession

_PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32


def _login(client: TestClient, code: str = "demo") -> None:
    response = client.get("/api/auth/callback", params={"code": code})
    assert response.status_code == 302


async def _tenant(session: MemorySession, org_id: str = "mock-org") -> Tenant:
    result = await session.exec(select(Tenant))
    return next(row for row in result.all() if row.nuna_org_id == org_id)


async def _reopen(session: MemorySession) -> Tenant:
    tenant = await _tenant(session)
    tenant.onboarding_completed = False
    session.add(tenant)
    await session.commit()
    return tenant


def _form(**overrides: str) -> dict[str, str]:
    payload = {
        "business_name": "Casa Norte",
        "rfc": "CNO010101AAA",
        "address": "Av. Mexico 10, Guadalajara",
        "min_guests": "20",
        "max_guests": "200",
        "whatsapp_phone": "+523312345678",
        "contact_phone": "+523398765432",
        "show_prices_public": "on",
        "max_concurrent_events_per_slot": "2",
        "accepts_cash": "on",
        "accepts_transfer": "on",
        "transfer_instructions": "CLABE 012345678901234567",
        "day_0": "on",
        "start_0": "10:00",
        "end_0": "18:00",
    }
    payload.update(overrides)
    return payload


def _logo(
    name: str = "logo.png", body: bytes = _PNG, mime: str = "image/png"
) -> dict[str, tuple[str, bytes, str]]:
    return {"logo": (name, body, mime)}


async def test_dashboard_without_onboarding_redirects(
    client: TestClient, memory_db: MemorySession
) -> None:
    _login(client)
    await _reopen(memory_db)
    panel = client.get("/dashboard/menu/recipes")
    assert panel.status_code == 302
    assert panel.headers["location"] == "/dashboard/onboarding"
    asset = client.get("/dashboard/assets/app.js")
    assert asset.status_code == 200
    wizard = client.get("/onboarding")
    assert wizard.status_code == 302
    assert wizard.headers["location"] == "/dashboard/onboarding"
    page = client.get("/dashboard/onboarding")
    assert page.status_code == 200


async def test_finished_onboarding_stays_on_the_dashboard(
    client: TestClient,
) -> None:
    _login(client)
    panel = client.get("/dashboard")
    assert panel.status_code == 200
    wizard = client.get("/onboarding")
    assert wizard.status_code == 302
    assert wizard.headers["location"] == "/dashboard"
    session = client.get("/api/auth/session")
    assert session.json()["onboarding_completed"] is True


def test_superuser_skips_the_wizard(client: TestClient) -> None:
    _login(client, "admin")
    panel = client.get("/dashboard")
    assert panel.status_code == 302
    assert panel.headers["location"] == "/admin"
    wizard = client.get("/onboarding")
    assert wizard.status_code == 302
    assert wizard.headers["location"] == "/admin"


async def test_duplicate_rfc_and_whatsapp_are_rejected(
    client: TestClient, memory_db: MemorySession
) -> None:
    _login(client)
    await _reopen(memory_db)
    memory_db.add(
        Tenant(
            nuna_org_id="other-org",
            slug="otra-casa",
            business_name="Otra Casa",
            rfc="CNO010101AAA",
            whatsapp_phone="+523312345678",
        )
    )
    rfc = client.post("/onboarding/complete", data=_form(), files=_logo())
    assert rfc.status_code == 409
    assert "RFC" in rfc.text
    phone = client.post(
        "/onboarding/complete",
        data=_form(rfc="OTR010101AAA", whatsapp_phone="+523312345678"),
        files=_logo(),
    )
    assert phone.status_code == 409
    assert "WhatsApp" in phone.text


async def test_logo_type_and_weight_are_rejected(
    client: TestClient, memory_db: MemorySession
) -> None:
    _login(client)
    await _reopen(memory_db)
    kind = client.post(
        "/onboarding/complete",
        data=_form(),
        files=_logo("nota.txt", b"hola", "text/plain"),
    )
    assert kind.status_code == 422
    assert "PNG" in kind.text
    heavy = _PNG + b"\x00" * (5 * 1024 * 1024)
    weight = client.post(
        "/onboarding/complete",
        data=_form(),
        files=_logo(body=heavy),
    )
    assert weight.status_code == 422
    assert "5 MB" in weight.text


async def test_eligible_trial_opens_the_dashboard(
    client: TestClient, memory_db: MemorySession, monkeypatch: MonkeyPatch
) -> None:
    _login(client)
    await _reopen(memory_db)
    revoked: list[str] = []

    async def revoke(*_args: object, **_kwargs: object) -> None:
        revoked.append("revoke")

    monkeypatch.setattr(
        "app.services.onboarding_service.nuna_client.revoke_trial_eligibility",
        revoke,
    )
    done = client.post("/onboarding/complete", data=_form(), files=_logo())
    assert done.status_code == 302
    assert done.headers["location"] == "/dashboard"
    assert revoked == []
    tenant = await _tenant(memory_db)
    assert tenant.onboarding_completed is True
    assert tenant.has_active_plan is True
    assert tenant.logo_url == f"/uploads/logos/{tenant.id}.png"
    warehouses = await memory_db.exec(select(Warehouse))
    primary = [row for row in warehouses.all() if row.is_primary]
    assert len(primary) == 1
    assert primary[0].name == "Almacén Principal"
    again = client.get("/onboarding")
    assert again.status_code == 302
    assert again.headers["location"] == "/dashboard"


async def test_consumed_trial_sends_the_provider_to_billing(
    client: TestClient, memory_db: MemorySession, monkeypatch: MonkeyPatch
) -> None:
    _login(client)
    await _reopen(memory_db)
    revoked: list[tuple[object, ...]] = []

    async def used(*_args: object, **_kwargs: object) -> bool:
        return False

    async def revoke(*args: object, **_kwargs: object) -> None:
        revoked.append(args)

    monkeypatch.setattr(
        "app.services.onboarding_service.nuna_client.check_trial_eligibility",
        used,
    )
    monkeypatch.setattr(
        "app.services.onboarding_service.nuna_client.revoke_trial_eligibility",
        revoke,
    )
    done = client.post(
        "/onboarding/complete",
        data=_form(rfc="USD010101AAA", whatsapp_phone="+523300000000"),
        files=_logo(),
    )
    assert done.status_code == 302
    assert done.headers["location"] == "/dashboard"
    assert revoked
    tenant = await _tenant(memory_db)
    assert tenant.onboarding_completed is True
    assert tenant.has_active_plan is False


def test_business_profile_update(client: TestClient) -> None:
    _login(client)
    saved = client.patch(
        "/api/v1/operations/profile",
        json={
            "address": "Av. Americas 120, Guadalajara",
            "whatsapp_phone": "+523312345678",
            "contact_phone": "+523398765432",
            "min_guests": 15,
            "max_guests": 180,
            "accepts_cash": True,
            "accepts_transfer": True,
            "transfer_instructions": "CLABE 012345678901234567",
            "show_prices_public": True,
        },
    )
    assert saved.status_code == 200, saved.text
    body = saved.json()
    assert body["address"] == "Av. Americas 120, Guadalajara"
    assert body["whatsapp_phone"] == "+523312345678"
    assert body["min_guests"] == 15
    again = client.get("/api/v1/operations/profile")
    assert again.status_code == 200
    assert again.json()["max_guests"] == 180
