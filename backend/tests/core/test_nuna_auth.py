from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import jwt
import pytest
from fastapi import HTTPException

from app.core.config import settings
from app.core.nuna_auth import (
    StaticJWKClient,
    default_mock_claims,
    exchange_nuna_code,
    mock_jwks,
    organization_from_claims,
    reset_jwks_client,
    sign_mock_token,
    verify_nuna_jwt,
)
from app.core.security import decrypt_session, encrypt_session


def test_session_cookie_roundtrip() -> None:
    token = encrypt_session("nuna-jwt")
    assert decrypt_session(token) == "nuna-jwt"


def test_mock_token_verifies_for_ibistro_audience() -> None:
    claims = verify_nuna_jwt(sign_mock_token(default_mock_claims()))
    assert claims["aud"] == "ibistro"
    org = organization_from_claims(claims)
    assert org["nuna_org_id"] == "mock-org"
    assert org["has_active_plan"] is True


def test_wrong_audience_is_rejected() -> None:
    claims = default_mock_claims()
    claims["aud"] = "specular"
    with pytest.raises(HTTPException) as exc:
        verify_nuna_jwt(sign_mock_token(claims), client=StaticJWKClient(mock_jwks()))
    assert exc.value.status_code == 401


def test_organization_falls_back_to_subject_and_subscription() -> None:
    org = organization_from_claims(
        {
            "sub": "user-1",
            "email": "ana@example.com",
            "subscription": {"status": "active"},
        }
    )
    assert org["nuna_org_id"] == "user-1"
    assert org["business_name"] == "ana@example.com"
    assert org["has_active_plan"] is True


def test_explicit_inactive_plan_claim() -> None:
    org = organization_from_claims(
        {
            "sub": "org-9",
            "organization": {
                "id": "org-9",
                "business_name": "La Mesa",
                "has_active_plan": False,
            },
        }
    )
    assert org["has_active_plan"] is False
    assert org["business_name"] == "La Mesa"


def test_organization_reads_profile_fields() -> None:
    org = organization_from_claims(
        {
            "sub": "ignored",
            "has_active_plan": True,
            "organization": {
                "id": "org-7",
                "business_name": "  ",
                "rfc": "ABC010101AAA",
                "address": "Colima",
                "logo_url": "https://cdn.example/logo.png",
                "has_active_plan": False,
            },
        }
    )
    assert org["nuna_org_id"] == "org-7"
    assert org["business_name"] == "Proveedor"
    assert org["rfc"] == "ABC010101AAA"
    assert org["logo_url"] == "https://cdn.example/logo.png"
    assert org["has_active_plan"] is False
    with pytest.raises(HTTPException) as exc:
        organization_from_claims({"email": "ana@example.com"})
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_exchange_sends_confidential_client_without_pkce(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    class DummyResponse:
        status_code = 200
        text = ""

        def json(self) -> dict[str, str]:
            return {"access_token": "signed-token"}

    class DummyClient:
        def __init__(self, *args: object, **kwargs: object) -> None:
            del args, kwargs

        async def __aenter__(self) -> DummyClient:
            return self

        async def __aexit__(self, *args: object) -> None:
            del args

        async def post(self, url: str, data: dict[str, str]) -> DummyResponse:
            captured["url"] = url
            captured["data"] = data
            return DummyResponse()

    monkeypatch.setattr(settings, "MOCK_MODE", False)
    monkeypatch.setattr(httpx, "AsyncClient", DummyClient)
    token = await exchange_nuna_code(
        "auth-code", "https://ibistro.mx/api/auth/callback"
    )
    assert token == "signed-token"
    assert captured["url"] == settings.NUNA_TOKEN_URL
    body = captured["data"]
    assert body["grant_type"] == "authorization_code"
    assert body["client_id"] == settings.NUNA_CLIENT_ID
    assert body["client_secret"] == settings.NUNA_CLIENT_SECRET
    assert "code_verifier" not in body
    assert "code_challenge" not in body


@pytest.mark.asyncio
async def test_exchange_rejects_token_endpoint_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class DummyResponse:
        status_code = 401
        text = "nope"

        def json(self) -> dict[str, str]:
            return {}

    class DummyClient:
        def __init__(self, *args: object, **kwargs: object) -> None:
            del args, kwargs

        async def __aenter__(self) -> DummyClient:
            return self

        async def __aexit__(self, *args: object) -> None:
            del args

        async def post(self, url: str, data: dict[str, str]) -> DummyResponse:
            del url, data
            return DummyResponse()

    monkeypatch.setattr(settings, "MOCK_MODE", False)
    monkeypatch.setattr(httpx, "AsyncClient", DummyClient)
    with pytest.raises(HTTPException) as exc:
        await exchange_nuna_code("auth-code", settings.NUNA_REDIRECT_URI)
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_exchange_rejects_empty_access_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class DummyResponse:
        status_code = 200
        text = ""

        def json(self) -> dict[str, str]:
            return {}

    class DummyClient:
        def __init__(self, *args: object, **kwargs: object) -> None:
            del args, kwargs

        async def __aenter__(self) -> DummyClient:
            return self

        async def __aexit__(self, *args: object) -> None:
            del args

        async def post(self, url: str, data: dict[str, str]) -> DummyResponse:
            del url, data
            return DummyResponse()

    monkeypatch.setattr(settings, "MOCK_MODE", False)
    monkeypatch.setattr(httpx, "AsyncClient", DummyClient)
    with pytest.raises(HTTPException) as exc:
        await exchange_nuna_code("auth-code", settings.NUNA_REDIRECT_URI)
    assert exc.value.detail == "Nuna token response was empty"


def test_live_jwks_client_is_cached(monkeypatch: pytest.MonkeyPatch) -> None:
    reset_jwks_client()
    monkeypatch.setattr(settings, "MOCK_MODE", False)
    created: list[str] = []

    class FakeClient:
        def __init__(self, url: str) -> None:
            created.append(url)

    monkeypatch.setattr(jwt, "PyJWKClient", FakeClient)
    from app.core import nuna_auth

    first = nuna_auth.jwks_client()
    second = nuna_auth.jwks_client()
    assert first is second
    assert created == [settings.NUNA_JWKS_URL]
    reset_jwks_client()
    monkeypatch.setattr(settings, "MOCK_MODE", True)


def test_default_secret_is_rejected_outside_development(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "FASTAPI_ENV", None)
    with pytest.raises(ValueError):
        settings._check_default_secret("SECRET_KEY", "changethis")


def test_expired_token_is_rejected() -> None:
    claims = default_mock_claims()
    claims["exp"] = datetime.now(UTC) - timedelta(minutes=5)
    with pytest.raises(HTTPException):
        verify_nuna_jwt(sign_mock_token(claims))
