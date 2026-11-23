import pytest
from fastapi.testclient import TestClient

from app.api.routes.auth import _safe_return_to
from app.core.config import settings
from app.core.nuna_auth import default_mock_claims, sign_mock_token
from app.core.redis import claim_webhook_event
from app.core.security import encrypt_session


def test_webhook_rejects_invalid_secret(client: TestClient) -> None:
    response = client.post(
        "/webhooks/nuna",
        json={
            "nuna_org_id": "missing",
            "has_active_plan": False,
            "event": "payment.failed",
        },
        headers={"Authorization": "Bearer wrong-secret"},
    )
    assert response.status_code == 401


def test_webhook_requires_configured_secret(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "NUNA_WEBHOOK_SECRET", "")
    response = client.post(
        "/webhooks/nuna",
        json={
            "nuna_org_id": "missing",
            "has_active_plan": True,
            "event": "trial.started",
        },
        headers={"Authorization": "Bearer anything"},
    )
    assert response.status_code == 503


def test_login_redirect_and_logout_do_not_touch_the_database(
    client: TestClient,
) -> None:
    missing = client.get("/api/auth/callback")
    assert missing.status_code == 302
    assert missing.headers["location"].startswith(settings.NUNA_LOGIN_URL)
    assert "code_challenge" not in missing.headers["location"]

    anonymous = client.get("/api/auth/session")
    assert anonymous.status_code == 401

    client.cookies.set(settings.SESSION_COOKIE_NAME, "not-a-fernet-token")
    garbage = client.get("/api/auth/session")
    assert garbage.status_code == 401

    logout = client.get("/api/auth/logout")
    assert logout.status_code == 302
    assert settings.NUNA_LOGOUT_URL in logout.headers["location"]


def test_return_to_rejects_external_urls() -> None:
    assert _safe_return_to("/dashboard") == "/dashboard"
    assert _safe_return_to("https://evil.example") == "/dashboard/menu"
    assert _safe_return_to("//evil.example") == "/dashboard/menu"
    assert _safe_return_to("/\\\\trap") == "/dashboard/menu"
    assert _safe_return_to(None) == "/dashboard/menu"


@pytest.mark.asyncio
async def test_webhook_idempotency_fails_open_without_redis(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class BrokenRedis:
        async def set(self, *args: object, **kwargs: object) -> bool:
            del args, kwargs
            raise ConnectionError("redis down")

    monkeypatch.setattr("app.core.redis.get_redis", lambda: BrokenRedis())
    assert await claim_webhook_event("evt-1") is True

    class RecordingRedis:
        def __init__(self, stored: bool) -> None:
            self.stored = stored

        async def set(self, *args: object, **kwargs: object) -> bool | None:
            del args, kwargs
            if self.stored:
                return True
            return None

    monkeypatch.setattr("app.core.redis.get_redis", lambda: RecordingRedis(True))
    assert await claim_webhook_event("evt-2") is True
    monkeypatch.setattr("app.core.redis.get_redis", lambda: RecordingRedis(False))
    assert await claim_webhook_event("evt-3") is False


def _auth(secret: str | None = None) -> dict[str, str]:
    return {"Authorization": f"Bearer {secret or settings.NUNA_WEBHOOK_SECRET}"}


def test_protected_routes_require_a_session(client: TestClient) -> None:
    assert client.get("/api/v1/operations/ping").status_code == 401
    assert client.get("/api/v1/subscription/status").status_code == 401


def test_webhook_updates_plan_and_ignores_duplicates(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: set[str] = set()

    async def claim(event_id: str) -> bool:
        if event_id in seen:
            return False
        seen.add(event_id)
        return True

    monkeypatch.setattr("app.api.routes.webhooks.claim_webhook_event", claim)
    callback = client.get("/api/auth/callback?code=demo&return_to=/dashboard")
    assert callback.status_code == 302
    assert callback.headers["location"] == "/dashboard"

    session = client.get("/api/auth/session")
    assert session.status_code == 200
    body = session.json()
    assert body["authenticated"] is True
    assert body["has_active_plan"] is True
    assert body["slug"]

    ping = client.get("/api/v1/operations/ping")
    assert ping.status_code == 200

    suspended = client.post(
        "/webhooks/nuna",
        json={
            "nuna_org_id": body["nuna_org_id"],
            "has_active_plan": False,
            "event": "subscription.suspended",
            "event_id": "evt-suspend",
        },
        headers=_auth(),
    )
    assert suspended.status_code == 200
    assert suspended.json()["has_active_plan"] is False

    blocked = client.get("/api/v1/operations/ping")
    assert blocked.status_code == 403
    assert blocked.json()["detail"]["message"] == "Suscripción inactiva — Ir a Nuna"

    status = client.get("/api/v1/subscription/status")
    assert status.status_code == 200
    assert status.json()["has_active_plan"] is False

    duplicate = client.post(
        "/webhooks/nuna",
        json={
            "nuna_org_id": body["nuna_org_id"],
            "has_active_plan": True,
            "event": "payment.succeeded",
            "event_id": "evt-suspend",
        },
        headers=_auth(),
    )
    assert duplicate.json()["status"] == "duplicate"
    still_blocked = client.get("/api/v1/operations/ping")
    assert still_blocked.status_code == 403


def test_webhook_unknown_tenant(client: TestClient) -> None:
    response = client.post(
        "/webhooks/nuna",
        json={
            "nuna_org_id": "does-not-exist",
            "has_active_plan": True,
            "event": "trial.started",
        },
        headers=_auth(),
    )
    assert response.status_code == 404


def test_unknown_session_tenant_is_rejected(client: TestClient) -> None:
    claims = default_mock_claims()
    claims["sub"] = "ghost-org"
    claims["organization"] = {
        "id": "ghost-org",
        "business_name": "Ghost",
        "has_active_plan": True,
    }
    token = encrypt_session(sign_mock_token(claims))
    client.cookies.set(settings.SESSION_COOKIE_NAME, token)
    response = client.get("/api/v1/operations/ping")
    assert response.status_code == 401


def test_callback_keeps_slug_on_second_login(client: TestClient) -> None:
    first = client.get("/api/auth/callback?code=again")
    assert first.status_code == 302
    slug = client.get("/api/auth/session").json()["slug"]
    second = client.get("/api/auth/callback?code=again")
    assert second.status_code == 302
    assert client.get("/api/auth/session").json()["slug"] == slug
