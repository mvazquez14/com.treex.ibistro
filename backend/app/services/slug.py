import re
import unicodedata

SLUG_MAX_LENGTH = 80

RESERVED_SLUGS = frozenset(
    {
        "api",
        "admin",
        "dashboard",
        "c",
        "webhooks",
        "auth",
        "static",
        "docs",
        "health",
        "www",
        "redoc",
        "openapi",
        "login",
        "assets",
    }
)


def slugify(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_text.lower()).strip("-")
    slug = re.sub(r"-{2,}", "-", slug)
    if not slug:
        slug = "proveedor"
    return slug[:SLUG_MAX_LENGTH].strip("-") or "proveedor"


def next_available_slug(business_name: str, taken: set[str]) -> str:
    base = slugify(business_name)
    if base in RESERVED_SLUGS:
        base = _fit(f"{base}-proveedor")
    candidate = base
    suffix = 2
    while candidate in taken or candidate in RESERVED_SLUGS:
        candidate = _fit(base, suffix)
        suffix += 1
        if suffix > 10_000:
            raise RuntimeError("Unable to allocate a unique slug")
    return candidate


def _fit(base: str, suffix: int | None = None) -> str:
    if suffix is None:
        return base[:SLUG_MAX_LENGTH].strip("-") or "proveedor"
    tail = f"-{suffix}"
    trimmed = base[: SLUG_MAX_LENGTH - len(tail)].strip("-") or "proveedor"
    return f"{trimmed}{tail}"
