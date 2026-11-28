from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_session
from app.main import app
from tests.memory_db import MemorySession, SessionScope


@pytest.fixture(autouse=True)
def memory_db(monkeypatch: pytest.MonkeyPatch) -> Generator[MemorySession]:
    session = MemorySession()
    scope = SessionScope(session)
    monkeypatch.setattr("app.core.db.async_session_maker", scope)
    monkeypatch.setattr("app.seed.async_session_maker", scope)

    async def override() -> Generator[MemorySession]:
        yield session

    app.dependency_overrides[get_session] = override
    yield session
    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def _complete_onboarding_after_login(monkeypatch: pytest.MonkeyPatch) -> None:
    """Existing suites log in as an already configured provider."""
    from app.core.nuna_auth import upsert_tenant_from_claims

    async def wrapped(*, session: object, claims: dict[str, object]) -> object:
        tenant = await upsert_tenant_from_claims(session=session, claims=claims)  # type: ignore[arg-type]
        tenant.onboarding_completed = True
        session.add(tenant)  # type: ignore[attr-defined]
        await session.commit()  # type: ignore[attr-defined]
        return tenant

    monkeypatch.setattr("app.api.routes.auth.upsert_tenant_from_claims", wrapped)


@pytest.fixture
def client() -> Generator[TestClient]:
    with TestClient(app, follow_redirects=False) as test_client:
        yield test_client
