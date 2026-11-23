import uuid

import pytest
from fastapi.testclient import TestClient

from app.api.deps import tenant_is_available
from app.models import Tenant, WarehouseStock
from app.services.tenants import allocate_unique_slug
from app.utils import (
    generate_new_account_email,
    generate_password_reset_token,
    generate_reset_password_email,
    generate_test_email,
    send_email,
    verify_password_reset_token,
)


def test_available_stock_is_physical_minus_committed() -> None:
    stock = WarehouseStock(
        tenant_id=uuid.uuid4(),
        warehouse_id=uuid.uuid4(),
        ingredient_id=uuid.uuid4(),
        physical_stock=8.5,
        committed_stock=3.0,
    )
    assert stock.available_stock == 5.5


def test_tenant_is_available_follows_the_plan_flag() -> None:
    inactive = Tenant(
        nuna_org_id="org",
        slug="org",
        business_name="Org",
        has_active_plan=False,
    )
    active = Tenant(
        nuna_org_id="org-2",
        slug="org-2",
        business_name="Org",
        has_active_plan=True,
    )
    assert tenant_is_available(inactive) is False
    assert tenant_is_available(active) is True


def test_email_helpers_render_templates() -> None:
    test_email = generate_test_email("ana@example.com")
    assert "ana@example.com" in test_email.html_content
    reset = generate_reset_password_email("ana@example.com", "ana@example.com", "tok")
    assert "reset-password?token=tok" in reset.html_content
    account = generate_new_account_email("ana@example.com", "ana", "secret")
    assert "secret" in account.html_content
    token = generate_password_reset_token("ana@example.com")
    assert verify_password_reset_token(token) == "ana@example.com"
    assert verify_password_reset_token("not-a-token") is None


def test_send_email_builds_smtp_message(monkeypatch: pytest.MonkeyPatch) -> None:
    sent: dict[str, object] = {}

    class FakeMessage:
        def __init__(self, **kwargs: object) -> None:
            sent["init"] = kwargs

        def send(self, to: str, smtp: dict[str, object]) -> bool:
            sent["to"] = to
            sent["smtp"] = smtp
            return True

    monkeypatch.setattr("app.utils.emails.message.Message", FakeMessage)
    send_email(email_to="ana@example.com", subject="Hola", html_content="<p>Hola</p>")
    assert sent["to"] == "ana@example.com"


def test_health_check_reports_redis(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def healthy() -> bool:
        return True

    monkeypatch.setattr("app.api.routes.utils.ping_redis", healthy)
    assert client.get("/api/v1/utils/health-check/").status_code == 200

    async def down() -> bool:
        raise ConnectionError("redis down")

    monkeypatch.setattr("app.api.routes.utils.ping_redis", down)
    assert client.get("/api/v1/utils/health-check/").status_code == 503

    async def offline() -> bool:
        return False

    monkeypatch.setattr("app.api.routes.utils.ping_redis", offline)
    assert client.get("/api/v1/utils/health-check/").status_code == 503


class _Slugs:
    def __init__(self, values: list[str]) -> None:
        self.values = values

    def all(self) -> list[str]:
        return self.values


class _Session:
    def __init__(self, values: list[str]) -> None:
        self.values = values

    async def exec(self, statement: object) -> _Slugs:
        del statement
        return _Slugs(self.values)


@pytest.mark.asyncio
async def test_allocate_unique_slug_reads_existing_slugs() -> None:
    slug = await allocate_unique_slug(_Session(["cafe-del-centro"]), "Café del Centro")  # type: ignore[arg-type]
    assert slug == "cafe-del-centro-2"


def test_initial_data_entrypoint() -> None:
    from app.initial_data import init

    init()


@pytest.mark.asyncio
async def test_seed_is_idempotent() -> None:
    from sqlmodel import func, select

    from app.core.db import async_session_maker
    from app.models import ServiceCategory
    from app.seed import SERVICE_CATEGORIES, seed

    await seed()
    await seed()
    async with async_session_maker() as session:
        result = await session.exec(select(func.count()).select_from(ServiceCategory))
        assert result.one() == len(SERVICE_CATEGORIES)
