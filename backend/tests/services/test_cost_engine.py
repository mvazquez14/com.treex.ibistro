from decimal import Decimal
from uuid import uuid4

import pytest

from app.models.enums import PricingType
from app.services.cost_engine import (
    CostError,
    ExtraCharge,
    IngredientCost,
    PackageGroup,
    PackageOption,
    RecipeCost,
    RecipeLine,
    equipment_units,
    explode_recipe,
    gross_quantity,
    quote_package,
)


def test_gross_quantity_applies_waste_and_yield() -> None:
    assert gross_quantity(1.0, 0.2, 0.8) == 1.5625


def test_sub_recipe_at_half_portion_scales_to_half() -> None:
    ingredient_id = uuid4()
    sub_id = uuid4()
    parent_id = uuid4()
    ingredients = {
        ingredient_id: IngredientCost(ingredient_id, Decimal("8"), 0, 1),
    }
    recipes = {
        sub_id: RecipeCost(sub_id, 1, (RecipeLine(ingredient_id, None, 1),)),
        parent_id: RecipeCost(parent_id, 1, (RecipeLine(None, sub_id, 0.5),)),
    }
    lines = explode_recipe(parent_id, recipes, ingredients)
    assert lines[0].net_qty == 0.5
    assert lines[0].gross_qty == 0.5


def test_recipe_cycle_is_rejected() -> None:
    recipe_id = uuid4()
    recipes = {recipe_id: RecipeCost(recipe_id, 1, (RecipeLine(None, recipe_id, 1),))}
    with pytest.raises(CostError, match="ciclo"):
        explode_recipe(recipe_id, recipes, {})


def test_recipe_depth_above_eight_is_rejected() -> None:
    ids = [uuid4() for _ in range(9)]
    recipes = {
        recipe_id: RecipeCost(
            recipe_id,
            1,
            () if index == len(ids) - 1 else (RecipeLine(None, ids[index + 1], 1),),
        )
        for index, recipe_id in enumerate(ids)
    }
    with pytest.raises(CostError, match="profundidad"):
        explode_recipe(ids[0], recipes, {})


def test_fixed_group_includes_every_option_without_a_choice() -> None:
    rice = _ingredient("10")
    beans = _ingredient("6")
    rice_recipe = _recipe(rice)
    beans_recipe = _recipe(beans)
    group = PackageGroup(
        id=uuid4(),
        is_fixed=True,
        min_choices=0,
        max_choices=0,
        options=(
            PackageOption(rice_recipe.id, 1, Decimal("0")),
            PackageOption(beans_recipe.id, 1, Decimal("0")),
        ),
    )
    quoted = quote_package(
        guest_count=2,
        base_price_per_guest=Decimal("100"),
        groups=[group],
        selected_options={},
        recipes={rice_recipe.id: rice_recipe, beans_recipe.id: beans_recipe},
        ingredients={rice.id: rice, beans.id: beans},
    )
    assert {line.ingredient_id for line in quoted.explosion} == {rice.id, beans.id}
    assert quoted.price == Decimal("200.00")


def test_protein_group_rejects_two_or_four_choices() -> None:
    proteins = [_ingredient("20") for _ in range(5)]
    recipes = [_recipe(ingredient) for ingredient in proteins]
    group = PackageGroup(
        id=uuid4(),
        is_fixed=False,
        min_choices=3,
        max_choices=3,
        options=tuple(PackageOption(recipe.id, 1, Decimal("0")) for recipe in recipes),
    )
    common = {
        "guest_count": 1,
        "base_price_per_guest": Decimal("50"),
        "groups": [group],
        "recipes": {recipe.id: recipe for recipe in recipes},
        "ingredients": {ingredient.id: ingredient for ingredient in proteins},
    }
    with pytest.raises(CostError, match="3 porciones"):
        quote_package(
            selected_options={group.id: [recipe.id for recipe in recipes[:2]]},
            **common,
        )
    with pytest.raises(CostError, match="3 porciones"):
        quote_package(
            selected_options={group.id: [recipe.id for recipe in recipes[:4]]},
            **common,
        )
    quoted = quote_package(
        selected_options={group.id: [recipe.id for recipe in recipes[:3]]},
        **common,
    )
    assert len(quoted.explosion) == 3


def test_extras_multiply_by_guest_or_by_unit() -> None:
    ingredient = _ingredient("4")
    quoted = quote_package(
        guest_count=2,
        base_price_per_guest=Decimal("100"),
        groups=[],
        selected_options={},
        recipes={},
        ingredients={ingredient.id: ingredient},
        extras=[
            ExtraCharge(PricingType.PER_GUEST, Decimal("5"), 1, ingredient, None),
            ExtraCharge(PricingType.PER_UNIT, Decimal("20"), 3, None, None),
        ],
    )
    assert quoted.price_per_guest == Decimal("105.00")
    assert quoted.price == Decimal("270.00")
    assert quoted.explosion[0].net_qty == 2


def test_repeated_ingredient_lines_merge() -> None:
    ingredient = _ingredient("5")
    recipe = RecipeCost(
        uuid4(),
        1,
        (
            RecipeLine(ingredient.id, None, 1),
            RecipeLine(ingredient.id, None, 1),
        ),
    )
    lines = explode_recipe(recipe.id, {recipe.id: recipe}, {ingredient.id: ingredient})
    assert len(lines) == 1
    assert lines[0].net_qty == 2


def test_cost_engine_rejects_invalid_inputs() -> None:
    ingredient = _ingredient("4")
    recipe = _recipe(ingredient)
    group = PackageGroup(
        uuid4(),
        False,
        1,
        2,
        (PackageOption(recipe.id, 1, Decimal("0")),),
    )
    recipes = {recipe.id: recipe}
    ingredients = {ingredient.id: ingredient}
    with pytest.raises(CostError):
        quote_package(
            guest_count=0,
            base_price_per_guest=Decimal("10"),
            groups=[],
            selected_options={},
            recipes=recipes,
            ingredients=ingredients,
        )
    with pytest.raises(CostError):
        quote_package(
            guest_count=1,
            base_price_per_guest=Decimal("-1"),
            groups=[],
            selected_options={},
            recipes=recipes,
            ingredients=ingredients,
        )
    with pytest.raises(CostError):
        quote_package(
            guest_count=1,
            base_price_per_guest=Decimal("10"),
            groups=[group],
            selected_options={uuid4(): [recipe.id]},
            recipes=recipes,
            ingredients=ingredients,
        )
    with pytest.raises(CostError, match="entre 1 y 2"):
        quote_package(
            guest_count=1,
            base_price_per_guest=Decimal("10"),
            groups=[group],
            selected_options={group.id: []},
            recipes=recipes,
            ingredients=ingredients,
        )
    doubled = quote_package(
        guest_count=1,
        base_price_per_guest=Decimal("10"),
        groups=[group],
        selected_options={group.id: [recipe.id, recipe.id]},
        recipes=recipes,
        ingredients=ingredients,
    )
    assert doubled.price == Decimal("10.00")
    assert doubled.explosion[0].net_qty == 2
    with pytest.raises(CostError, match="entre 1 y 2"):
        quote_package(
            guest_count=1,
            base_price_per_guest=Decimal("10"),
            groups=[group],
            selected_options={group.id: [recipe.id, recipe.id, recipe.id]},
            recipes=recipes,
            ingredients=ingredients,
        )
    with pytest.raises(CostError, match="no pertenece"):
        quote_package(
            guest_count=1,
            base_price_per_guest=Decimal("10"),
            groups=[group],
            selected_options={group.id: [uuid4()]},
            recipes=recipes,
            ingredients=ingredients,
        )
    with pytest.raises(CostError):
        explode_recipe(recipe.id, recipes, ingredients, portions=-1)
    with pytest.raises(CostError):
        explode_recipe(
            recipe.id,
            {
                recipe.id: RecipeCost(
                    recipe.id, 1, (RecipeLine(ingredient.id, uuid4(), 1),)
                )
            },
            ingredients,
        )
    with pytest.raises(CostError):
        gross_quantity(-1, 0, 1)
    with pytest.raises(CostError):
        gross_quantity(1, 0.95, 1)
    with pytest.raises(CostError):
        gross_quantity(1, 0, 0.05)
    assert gross_quantity(0, 0, 1) == 0
    with pytest.raises(CostError):
        equipment_units(-1, 10)
    with pytest.raises(CostError):
        equipment_units(10, 0)
    with pytest.raises(CostError):
        quote_package(
            guest_count=1,
            base_price_per_guest=Decimal("10"),
            groups=[],
            selected_options={},
            recipes=recipes,
            ingredients=ingredients,
            extras=[ExtraCharge(PricingType.PER_UNIT, Decimal("1"), 0, None, None)],
        )
    pricey = IngredientCost(uuid4(), Decimal("-1"), 0, 1)
    with pytest.raises(CostError):
        explode_recipe(
            recipe.id,
            {recipe.id: RecipeCost(recipe.id, 1, (RecipeLine(pricey.id, None, 1),))},
            {pricey.id: pricey},
        )


def test_equipment_units_round_up() -> None:
    assert equipment_units(25, 25) == 1
    assert equipment_units(26, 25) == 2
    assert equipment_units(0, 25) == 0


def _ingredient(price: str) -> IngredientCost:
    return IngredientCost(uuid4(), Decimal(price), 0, 1)


def _recipe(ingredient: IngredientCost) -> RecipeCost:
    return RecipeCost(
        uuid4(),
        1,
        (RecipeLine(ingredient.id, None, 1),),
    )
