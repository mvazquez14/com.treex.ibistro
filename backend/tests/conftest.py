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


@pytest.fixture
def client() -> Generator[TestClient]:
    with TestClient(app, follow_redirects=False) as test_client:
        yield test_client
