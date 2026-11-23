from typing import Any

from sqlmodel import SQLModel

from app.models import ServiceCategory, Tenant


class MemoryResult:
    def __init__(self, rows: list[Any]) -> None:
        self.rows = rows

    def first(self) -> Any:
        return self.rows[0] if self.rows else None

    def all(self) -> list[Any]:
        return list(self.rows)

    def one(self) -> Any:
        return self.rows[0]


class MemorySession:
    def __init__(self) -> None:
        self.tenants: dict[str, Tenant] = {}
        self.categories: dict[str, ServiceCategory] = {}
        self.rows: dict[type[Any], dict[Any, Any]] = {}

    def add(self, obj: SQLModel) -> None:
        if isinstance(obj, Tenant):
            self.tenants[obj.nuna_org_id] = obj
        elif isinstance(obj, ServiceCategory):
            self.categories[obj.slug] = obj
        ident = getattr(obj, "id", None)
        if ident is not None:
            self.rows.setdefault(type(obj), {})[ident] = obj

    async def commit(self) -> None:
        return None

    async def rollback(self) -> None:
        return None

    async def flush(self) -> None:
        return None

    async def refresh(self, obj: SQLModel) -> None:
        del obj

    async def get(self, model: type[Any], ident: Any) -> Any:
        if model is Tenant:
            for tenant in self.tenants.values():
                if _same(tenant.id, ident):
                    return tenant
        bucket = self.rows.get(model, {})
        if ident in bucket:
            return bucket[ident]
        for key, value in bucket.items():
            if _same(key, ident):
                return value
        return None

    async def delete(self, obj: SQLModel) -> None:
        if isinstance(obj, Tenant):
            self.tenants.pop(obj.nuna_org_id, None)
        elif isinstance(obj, ServiceCategory):
            self.categories.pop(obj.slug, None)
        ident = getattr(obj, "id", None)
        bucket = self.rows.get(type(obj))
        if bucket is not None and ident is not None:
            bucket.pop(ident, None)

    async def exec(self, statement: Any) -> MemoryResult:
        description = statement.column_descriptions[0]
        entity = description.get("entity")
        name = description.get("name")
        params = statement.compile().params
        if name == "count":
            return MemoryResult([len(self.categories)])
        if entity is Tenant and name == "slug":
            return MemoryResult([tenant.slug for tenant in self.tenants.values()])
        if entity is Tenant:
            org_id = _param(params, "nuna_org_id")
            if org_id:
                tenant = self.tenants.get(org_id)
                return MemoryResult([tenant] if tenant else [])
            slug = _param(params, "slug")
            if slug:
                matches = [
                    tenant for tenant in self.tenants.values() if tenant.slug == slug
                ]
                return MemoryResult(matches)
            return MemoryResult(list(self.tenants.values()))
        if entity is ServiceCategory:
            slug = _param(params, "slug")
            if slug:
                category = self.categories.get(slug)
                return MemoryResult([category] if category else [])
            return MemoryResult(list(self.categories.values()))
        if entity is None:
            return MemoryResult([])
        matched = [
            row
            for row in self.rows.get(entity, {}).values()
            if _row_matches(row, params)
        ]
        return MemoryResult(matched)


def _param(params: dict[str, Any], prefix: str) -> str | None:
    for key, value in params.items():
        if key == prefix or key.startswith(f"{prefix}_"):
            return str(value)
    return None


def _field_name(key: str) -> str:
    name = key
    while True:
        head, sep, tail = name.rpartition("_")
        if sep and tail.isdigit():
            name = head
            continue
        return name


def _same(left: Any, right: Any) -> bool:
    if left == right:
        return True
    if left is None or right is None:
        return False
    return str(left) == str(right)


def _row_matches(row: Any, params: dict[str, Any]) -> bool:
    for key, expected in params.items():
        field = _field_name(key)
        if not hasattr(row, field):
            continue
        if not _same(getattr(row, field), expected):
            return False
    return True


class SessionScope:
    def __init__(self, session: MemorySession) -> None:
        self.session = session

    def __call__(self) -> SessionScope:
        return self

    async def __aenter__(self) -> MemorySession:
        return self.session

    async def __aexit__(self, *args: object) -> None:
        del args
