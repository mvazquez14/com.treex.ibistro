import re
from decimal import Decimal
from uuid import uuid4

from fastapi.testclient import TestClient

from app.models import IngredientUnit, Recipe, ServiceCategory
from tests.memory_db import MemorySession


def _login(client: TestClient) -> None:
    response = client.get("/api/auth/callback", params={"code": "demo"})
    assert response.status_code == 302


def test_dashboard_pages_are_spanish_for_an_active_plan(client: TestClient) -> None:
    _login(client)
    pages = {
        "/dashboard/menu": "Costo por porción",
        "/dashboard/warehouses": "Kardex",
        "/dashboard/equipment": "Unidades",
        "/dashboard/quotes": "Cotizaciones",
        "/dashboard/reservations": "Saldo pendiente",
        "/dashboard/pos": "Efectivo",
        "/dashboard/reports": "Rentabilidad real",
    }
    for path, marker in pages.items():
        response = client.get(path)
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        assert marker in response.text
        assert 'lang="es"' in response.text


def test_dashboard_recipe_and_purchase_round_trip(client: TestClient) -> None:
    _login(client)
    recipe = client.post(
        "/dashboard/menu/recipes",
        data={"name": "Tinga", "portion_size": "1", "portion_unit": "porción"},
    )
    assert recipe.status_code == 200
    assert "Tinga" in recipe.text
    assert "Costo por porción" in recipe.text

    warehouse = client.post(
        "/dashboard/warehouses/sites",
        data={"name": "Central", "is_primary": "true"},
    )
    assert warehouse.status_code == 200
    assert "Central" in warehouse.text
    ingredient = client.post(
        "/dashboard/warehouses/ingredients",
        data={
            "name": "Pollo",
            "unit": "kg",
            "purchase_price": "80",
            "waste_factor": "0.2",
            "cooking_yield_factor": "0.8",
            "min_stock": "0",
            "max_stock": "10",
        },
    )
    assert ingredient.status_code == 200
    assert "Pollo" in ingredient.text

    screen = client.get("/dashboard/warehouses")
    warehouse_id = _option_value(screen.text, "warehouse_id")
    ingredient_id = _option_value(screen.text, "ingredient_id")
    movement = client.post(
        "/dashboard/warehouses/movements",
        data={
            "warehouse_id": warehouse_id,
            "ingredient_id": ingredient_id,
            "movement_type": "PURCHASE_IN",
            "quantity": "2",
        },
    )
    assert movement.status_code == 200
    assert "Compra" in movement.text
    assert "Disponible" in movement.text

    asset = client.post(
        "/dashboard/equipment/assets",
        data={
            "name": "Chafer",
            "category": "Calentamiento",
            "total_stock": "4",
            "rental_price_per_unit": "0",
            "replacement_cost": "800",
        },
    )
    assert asset.status_code == 200
    assert "Chafer" in asset.text
    preview = client.get("/dashboard/equipment", params={"guests": 26})
    assert preview.status_code == 200
    assert "unidades para" in preview.text or "Unidades" in preview.text


def test_tenant_cannot_read_or_change_another_tenants_recipe(
    client: TestClient, memory_db: MemorySession
) -> None:
    _login(client)
    created = client.post(
        "/api/v1/menu/recipes",
        json={
            "name": "Privada",
            "portion_size": 1,
            "portion_unit": "pz",
            "is_sub_recipe": False,
        },
    )
    assert created.status_code == 201
    foreign = Recipe(
        tenant_id=uuid4(),
        name="Ajena",
        portion_size=1,
        portion_unit="pz",
    )
    memory_db.add(foreign)
    listed = client.get("/api/v1/menu/recipes")
    names = [row["name"] for row in listed.json()]
    assert "Privada" in names
    assert "Ajena" not in names
    missing = client.delete(f"/api/v1/menu/recipes/{foreign.id}")
    assert missing.status_code == 404


def test_recipe_with_a_line_cannot_be_deleted(client: TestClient) -> None:
    _login(client)
    ingredient = client.post(
        "/api/v1/warehouses/ingredients",
        json={
            "name": "Cebolla",
            "unit": IngredientUnit.KG,
            "purchase_price": "12.00",
            "min_stock": 0,
            "max_stock": 5,
            "waste_factor": 0,
            "cooking_yield_factor": 1,
        },
    )
    assert ingredient.status_code == 201
    recipe = client.post(
        "/api/v1/menu/recipes",
        json={"name": "Salsa", "portion_size": 1, "portion_unit": "lt"},
    )
    assert recipe.status_code == 201
    item = client.post(
        f"/api/v1/menu/recipes/{recipe.json()['id']}/items",
        json={
            "ingredient_id": ingredient.json()["id"],
            "net_qty_per_portion": 0.2,
        },
    )
    assert item.status_code == 201
    assert Decimal(item.json()["cost_per_portion"]) == Decimal("2.40")
    blocked = client.delete(f"/api/v1/menu/recipes/{recipe.json()['id']}")
    assert blocked.status_code == 409
    removed = client.delete(
        f"/api/v1/menu/recipe-items/{item.json()['items'][0]['id']}"
    )
    assert removed.status_code == 204
    deleted = client.delete(f"/api/v1/menu/recipes/{recipe.json()['id']}")
    assert deleted.status_code == 204


def test_supplier_phone_must_be_e164(client: TestClient) -> None:
    _login(client)
    response = client.post(
        "/api/v1/warehouses/suppliers",
        json={"name": "Abarrotes", "phone": "3312345678"},
    )
    assert response.status_code == 422
    assert "internacional" in response.json()["detail"]


def test_reserve_above_available_stock_is_conflict(client: TestClient) -> None:
    _login(client)
    warehouse = client.post(
        "/api/v1/warehouses",
        json={"name": "Central", "is_primary": True},
    )
    ingredient = client.post(
        "/api/v1/warehouses/ingredients",
        json={
            "name": "Arroz",
            "unit": "kg",
            "purchase_price": "10.00",
            "min_stock": 0,
            "max_stock": 10,
            "waste_factor": 0,
            "cooking_yield_factor": 1,
        },
    )
    assert warehouse.status_code == 201
    assert ingredient.status_code == 201
    purchase = client.post(
        "/api/v1/warehouses/movements",
        json={
            "warehouse_id": warehouse.json()["id"],
            "ingredient_id": ingredient.json()["id"],
            "movement_type": "PURCHASE_IN",
            "quantity": 5,
        },
    )
    assert purchase.status_code == 201
    reserve = client.post(
        "/api/v1/warehouses/movements",
        json={
            "warehouse_id": warehouse.json()["id"],
            "ingredient_id": ingredient.json()["id"],
            "movement_type": "COMMIT_RESERVE",
            "quantity": 2,
        },
    )
    assert reserve.status_code == 201
    stock = client.get("/api/v1/warehouses/stock")
    row = stock.json()[0]
    assert row["physical_stock"] == 5
    assert row["committed_stock"] == 2
    assert row["available_stock"] == 3
    rejected = client.post(
        "/api/v1/warehouses/movements",
        json={
            "warehouse_id": warehouse.json()["id"],
            "ingredient_id": ingredient.json()["id"],
            "movement_type": "COMMIT_RESERVE",
            "quantity": 4,
        },
    )
    assert rejected.status_code == 409


def test_package_quote_uses_categories(
    client: TestClient, memory_db: MemorySession
) -> None:
    _login(client)
    category = ServiceCategory(name="Taquiza", slug="taquiza-test", icon="")
    memory_db.add(category)
    recipe = client.post(
        "/api/v1/menu/recipes",
        json={"name": "Pastor", "portion_size": 1, "portion_unit": "pz"},
    )
    ingredient = client.post(
        "/api/v1/warehouses/ingredients",
        json={
            "name": "Carne",
            "unit": "kg",
            "purchase_price": "100.00",
            "min_stock": 0,
            "max_stock": 5,
            "waste_factor": 0.2,
            "cooking_yield_factor": 0.8,
        },
    )
    client.post(
        f"/api/v1/menu/recipes/{recipe.json()['id']}/items",
        json={"ingredient_id": ingredient.json()["id"], "net_qty_per_portion": 1},
    )
    package = client.post(
        "/api/v1/menu/packages",
        json={
            "category_id": str(category.id),
            "name": "Taquiza básica",
            "base_price_per_guest": "150.00",
            "min_guests": 20,
        },
    )
    assert package.status_code == 201
    grouped = client.post(
        f"/api/v1/menu/packages/{package.json()['id']}/groups",
        json={
            "group_name": "Guisos",
            "min_choices": 1,
            "max_choices": 1,
            "is_fixed": True,
        },
    )
    group_id = grouped.json()["groups"][0]["id"]
    client.post(
        f"/api/v1/menu/groups/{group_id}/options",
        json={"recipe_id": recipe.json()["id"], "portions_per_guest": 1},
    )
    quoted = client.post(
        f"/api/v1/menu/packages/{package.json()['id']}/quote",
        json={"guest_count": 2, "selected_options": {}},
    )
    assert quoted.status_code == 200
    body = quoted.json()
    assert Decimal(body["price"]) == Decimal("300.00")
    assert body["explosion"][0]["gross_qty"] == 3.125


def test_api_and_dashboard_cover_catalog_writes(
    client: TestClient, memory_db: MemorySession
) -> None:
    _login(client)
    category = ServiceCategory(name="Mexicana", slug="mexicana-crud", icon="")
    memory_db.add(category)

    supplier = _expect(
        client.post(
            "/api/v1/warehouses/suppliers",
            json={
                "name": "Central de abastos",
                "phone": "+523312345678",
                "email": "a@b.com",
            },
        ),
        201,
    )
    _expect(
        client.patch(
            f"/api/v1/warehouses/suppliers/{supplier['id']}",
            json={"contact_name": "Lupita", "notes": "Por la mañana"},
        ),
        200,
    )
    assert (
        client.patch(
            f"/api/v1/warehouses/suppliers/{supplier['id']}",
            json={"phone": "3312345678"},
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/dashboard/warehouses/suppliers",
            data={"name": "Mal", "phone": "123"},
        ).status_code
        == 422
    )

    primary = _expect(
        client.post("/api/v1/warehouses", json={"name": "Central", "is_primary": True}),
        201,
    )
    secondary = _expect(
        client.post(
            "/api/v1/warehouses",
            json={"name": "Anexo", "is_primary": True, "location_notes": "Patio"},
        ),
        201,
    )
    _expect(
        client.patch(
            f"/api/v1/warehouses/{primary['id']}",
            json={"name": "Central norte", "is_primary": False},
        ),
        200,
    )
    empty = _expect(client.post("/api/v1/warehouses", json={"name": "Vacío"}), 201)
    _expect(client.delete(f"/api/v1/warehouses/{empty['id']}"), 204)

    ingredient = _expect(
        client.post(
            "/api/v1/warehouses/ingredients",
            json={
                "name": "Chile",
                "unit": "kg",
                "purchase_price": "40.00",
                "sale_price": "60.00",
                "min_stock": 1,
                "max_stock": 8,
                "waste_factor": 0.1,
                "cooking_yield_factor": 1,
                "supplier_id": supplier["id"],
            },
        ),
        201,
    )
    _expect(
        client.patch(
            f"/api/v1/warehouses/ingredients/{ingredient['id']}",
            json={
                "name": "Chile guajillo",
                "clear_sale_price": True,
                "sale_price": None,
            },
        ),
        200,
    )
    spare = _expect(
        client.post(
            "/api/v1/warehouses/ingredients",
            json={
                "name": "Sal",
                "unit": "kg",
                "purchase_price": "5",
                "min_stock": 0,
                "max_stock": 1,
                "waste_factor": 0,
                "cooking_yield_factor": 1,
            },
        ),
        201,
    )
    _expect(client.delete(f"/api/v1/warehouses/ingredients/{spare['id']}"), 204)
    loose = _expect(
        client.post("/api/v1/warehouses/suppliers", json={"name": "Sin insumos"}),
        201,
    )
    _expect(client.delete(f"/api/v1/warehouses/suppliers/{loose['id']}"), 204)
    assert (
        client.delete(f"/api/v1/warehouses/suppliers/{supplier['id']}").status_code
        == 409
    )

    recipe = _expect(
        client.post(
            "/api/v1/menu/recipes",
            json={"name": "Adobo", "portion_size": 1, "portion_unit": "kg"},
        ),
        201,
    )
    sub = _expect(
        client.post(
            "/api/v1/menu/recipes",
            json={
                "name": "Base",
                "portion_size": 1,
                "portion_unit": "kg",
                "is_sub_recipe": True,
            },
        ),
        201,
    )
    _expect(client.get(f"/api/v1/menu/recipes/{recipe['id']}"), 200)
    _expect(
        client.patch(
            f"/api/v1/menu/recipes/{recipe['id']}",
            json={"name": "Adobo rojo", "portion_size": 2},
        ),
        200,
    )
    _expect(
        client.post(
            f"/api/v1/menu/recipes/{sub['id']}/items",
            json={"ingredient_id": ingredient["id"], "net_qty_per_portion": 1},
        ),
        201,
    )
    with_line = _expect(
        client.post(
            f"/api/v1/menu/recipes/{recipe['id']}/items",
            json={"sub_recipe_id": sub["id"], "net_qty_per_portion": 1},
        ),
        201,
    )
    assert (
        client.post(
            f"/api/v1/menu/recipes/{recipe['id']}/items",
            json={
                "ingredient_id": ingredient["id"],
                "sub_recipe_id": sub["id"],
                "net_qty_per_portion": 1,
            },
        ).status_code
        == 422
    )
    assert client.delete(f"/api/v1/menu/recipes/{sub['id']}").status_code == 409

    package = _expect(
        client.post(
            "/api/v1/menu/packages",
            json={
                "category_id": str(category.id),
                "name": "Banquete",
                "description": "Servicio completo",
                "base_price_per_guest": "200",
                "min_guests": 10,
            },
        ),
        201,
    )
    _expect(client.get(f"/api/v1/menu/packages/{package['id']}"), 200)
    _expect(
        client.patch(
            f"/api/v1/menu/packages/{package['id']}",
            json={"name": "Banquete de patio", "min_guests": 12, "is_active": True},
        ),
        200,
    )
    grouped = _expect(
        client.post(
            f"/api/v1/menu/packages/{package['id']}/groups",
            json={
                "group_name": "Guiso",
                "min_choices": 1,
                "max_choices": 1,
                "is_fixed": False,
            },
        ),
        201,
    )
    group_id = grouped["groups"][0]["id"]
    _expect(
        client.patch(
            f"/api/v1/menu/groups/{group_id}",
            json={"group_name": "Guiso principal", "max_choices": 1},
        ),
        200,
    )
    with_option = _expect(
        client.post(
            f"/api/v1/menu/groups/{group_id}/options",
            json={
                "recipe_id": recipe["id"],
                "portions_per_guest": 1,
                "extra_price_per_guest": "10",
            },
        ),
        201,
    )
    option_id = with_option["groups"][0]["options"][0]["id"]
    assert (
        client.post(
            f"/api/v1/menu/groups/{group_id}/options",
            json={"recipe_id": recipe["id"]},
        ).status_code
        == 409
    )
    assert (
        client.post(
            f"/api/v1/menu/packages/{package['id']}/quote",
            json={"guest_count": 2, "selected_options": {}},
        ).status_code
        == 422
    )
    chosen = client.post(
        f"/api/v1/menu/packages/{package['id']}/quote",
        json={"guest_count": 2, "selected_options": {group_id: [recipe["id"]]}},
    )
    assert chosen.status_code == 200
    assert client.delete(f"/api/v1/menu/packages/{package['id']}").status_code == 409
    assert client.delete(f"/api/v1/menu/groups/{group_id}").status_code == 409

    extra = _expect(
        client.post(
            "/api/v1/menu/extras",
            json={
                "name": "Agua",
                "unit_price": "12",
                "pricing_type": "PER_GUEST",
                "recipe_id": sub["id"],
            },
        ),
        201,
    )
    _expect(
        client.patch(
            f"/api/v1/menu/extras/{extra['id']}",
            json={"name": "Agua de jamaica", "is_active": False, "clear_recipe": True},
        ),
        200,
    )
    assert (
        client.post(
            "/api/v1/menu/extras",
            json={
                "name": "Mixto",
                "unit_price": "1",
                "pricing_type": "PER_UNIT",
                "ingredient_id": ingredient["id"],
                "recipe_id": recipe["id"],
            },
        ).status_code
        == 422
    )
    assert client.get("/api/v1/menu/extras").status_code == 200
    _expect(client.delete(f"/api/v1/menu/extras/{extra['id']}"), 204)

    asset = _expect(
        client.post(
            "/api/v1/equipment/assets",
            json={
                "name": "Mantel",
                "category": "Manteleria",
                "total_stock": 20,
                "rental_price_per_unit": "5",
                "replacement_cost": "80",
            },
        ),
        201,
    )
    _expect(
        client.patch(
            f"/api/v1/equipment/assets/{asset['id']}",
            json={"total_stock": 18, "name": "Mantel redondo"},
        ),
        200,
    )
    rule = _expect(
        client.post(
            "/api/v1/equipment/rules",
            json={
                "package_id": package["id"],
                "asset_id": asset["id"],
                "guests_per_unit": 10,
            },
            params={"guests": 26},
        ),
        201,
    )
    assert rule["units_for_guests"] == 3
    _expect(
        client.patch(
            f"/api/v1/equipment/rules/{rule['id']}",
            json={"guests_per_unit": 25},
            params={"guests": 26},
        ),
        200,
    )
    assert (
        client.get(
            "/api/v1/equipment/preview", params={"guests": 26, "guests_per_unit": 25}
        ).json()["units"]
        == 2
    )
    assert (
        client.get(
            "/api/v1/equipment/preview", params={"guests": 1, "guests_per_unit": 0}
        ).status_code
        == 422
    )
    assert client.delete(f"/api/v1/equipment/assets/{asset['id']}").status_code == 409
    _expect(client.delete(f"/api/v1/equipment/rules/{rule['id']}"), 204)
    _expect(client.delete(f"/api/v1/equipment/assets/{asset['id']}"), 204)
    _expect(client.delete(f"/api/v1/menu/options/{option_id}"), 204)
    _expect(client.delete(f"/api/v1/menu/groups/{group_id}"), 204)
    _expect(client.delete(f"/api/v1/menu/packages/{package['id']}"), 204)

    _expect(
        client.post(
            "/api/v1/warehouses/movements",
            json={
                "warehouse_id": secondary["id"],
                "ingredient_id": ingredient["id"],
                "movement_type": "PURCHASE_IN",
                "quantity": 10,
            },
        ),
        201,
    )
    _expect(
        client.post(
            "/api/v1/warehouses/movements",
            json={
                "warehouse_id": secondary["id"],
                "ingredient_id": ingredient["id"],
                "movement_type": "COMMIT_RESERVE",
                "quantity": 4,
            },
        ),
        201,
    )
    _expect(
        client.post(
            "/api/v1/warehouses/movements",
            json={
                "warehouse_id": secondary["id"],
                "ingredient_id": ingredient["id"],
                "movement_type": "COMMIT_RELEASE",
                "quantity": 1,
            },
        ),
        201,
    )
    _expect(
        client.post(
            "/api/v1/warehouses/movements",
            json={
                "warehouse_id": secondary["id"],
                "ingredient_id": ingredient["id"],
                "movement_type": "PRODUCTION_OUT",
                "quantity": 3,
            },
        ),
        201,
    )
    _expect(
        client.post(
            "/api/v1/warehouses/movements",
            json={
                "warehouse_id": secondary["id"],
                "ingredient_id": ingredient["id"],
                "movement_type": "POS_SALE_OUT",
                "quantity": 2,
            },
        ),
        201,
    )
    assert (
        client.post(
            "/api/v1/warehouses/movements",
            json={
                "warehouse_id": secondary["id"],
                "ingredient_id": ingredient["id"],
                "movement_type": "ADJUSTMENT",
                "quantity": 0,
            },
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/v1/warehouses/movements",
            json={
                "warehouse_id": secondary["id"],
                "ingredient_id": ingredient["id"],
                "movement_type": "POS_SALE_OUT",
                "quantity": 100,
            },
        ).status_code
        == 409
    )
    kardex = client.get(
        "/api/v1/warehouses/kardex",
        params={"warehouse_id": secondary["id"], "ingredient_id": ingredient["id"]},
    )
    assert kardex.status_code == 200
    assert len(kardex.json()) >= 4
    reserved = client.post(
        "/api/v1/warehouses/reservations",
        json={"recipe_id": sub["id"], "portions": 1},
    )
    assert reserved.status_code == 201
    assert client.delete(f"/api/v1/warehouses/{secondary['id']}").status_code == 409
    assert (
        client.delete(f"/api/v1/warehouses/ingredients/{ingredient['id']}").status_code
        == 409
    )

    page = client.post(
        f"/dashboard/menu/recipes/{recipe['id']}",
        data={"name": "Adobo de la casa", "portion_size": "2", "portion_unit": "kg"},
    )
    assert page.status_code == 200
    assert "Adobo de la casa" in page.text
    item_id = with_line["items"][0]["id"]
    assert (
        client.post(f"/dashboard/menu/recipe-items/{item_id}/delete").status_code == 200
    )
    assert (
        client.post(
            f"/dashboard/menu/recipes/{recipe['id']}/items",
            data={
                "ingredient_id": ingredient["id"],
                "sub_recipe_id": "",
                "net_qty_per_portion": "0.5",
            },
        ).status_code
        == 200
    )
    packaged = client.post(
        "/dashboard/menu/packages",
        data={
            "name": "Paquete tablero",
            "category_id": str(category.id),
            "description": "En el jardín",
            "base_price_per_guest": "90",
            "min_guests": "8",
            "is_active": "true",
        },
    )
    assert packaged.status_code == 200
    assert "Paquete tablero" in packaged.text
    client.post(
        "/dashboard/menu/extras",
        data={
            "name": "Refresco",
            "unit_price": "18",
            "pricing_type": "PER_UNIT",
            "ingredient_id": "",
            "recipe_id": "",
            "is_active": "true",
        },
    )
    client.post(
        "/dashboard/warehouses/suppliers",
        data={
            "name": "Verduras del mercado",
            "phone": "+523333334444",
            "contact_name": "Ana",
        },
    )
    client.post(
        f"/dashboard/warehouses/sites/{primary['id']}",
        data={
            "name": "Central actualizada",
            "location_notes": "Planta baja",
            "is_primary": "true",
        },
    )
    client.post(
        f"/dashboard/warehouses/ingredients/{ingredient['id']}",
        data={
            "name": "Chile guajillo",
            "unit": "kg",
            "purchase_price": "42",
            "min_stock": "1",
            "max_stock": "9",
            "waste_factor": "0.1",
            "cooking_yield_factor": "1",
            "supplier_id": supplier["id"],
        },
    )
    client.post(
        "/dashboard/equipment/assets",
        data={
            "name": "Silla",
            "category": "Mobiliario",
            "total_stock": "40",
            "rental_price_per_unit": "3",
            "replacement_cost": "25",
        },
    )


def _expect(response: object, status: int) -> dict[str, object]:
    assert getattr(response, "status_code", None) == status, getattr(
        response, "text", response
    )
    if status == 204:
        return {}
    body = response.json()  # type: ignore[attr-defined]
    assert isinstance(body, dict)
    return body


def _option_value(html: str, select_name: str) -> str:
    marker = f'name="{select_name}"'
    start = html.find(marker)
    assert start != -1
    chunk = html[start : start + 1200]
    for value in re.findall(r'value="([^"]*)"', chunk):
        if value:
            return value
    raise AssertionError(select_name)
