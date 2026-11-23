import pytest

from app.services.slug import RESERVED_SLUGS, next_available_slug, slugify


def test_slugify_strips_accents_and_punctuation() -> None:
    assert slugify("Café del Centro!") == "cafe-del-centro"


def test_slugify_empty_falls_back() -> None:
    assert slugify("***") == "proveedor"


def test_reserved_slug_gets_suffix() -> None:
    assert next_available_slug("Admin", set()) == "admin-proveedor"
    assert next_available_slug("C", set()) not in RESERVED_SLUGS


@pytest.mark.parametrize("reserved", ["api", "dashboard", "webhooks", "www"])
def test_reserved_words_are_not_allocated(reserved: str) -> None:
    assert next_available_slug(reserved, set()) != reserved


def test_collision_appends_numeric_suffix() -> None:
    taken = {"taquiza", "taquiza-2"}
    assert next_available_slug("Taquiza", taken) == "taquiza-3"


def test_long_name_keeps_room_for_suffix() -> None:
    name = "a" * 200
    slug = next_available_slug(name, {slugify(name)})
    assert len(slug) <= 80
    assert slug.endswith("-2")
