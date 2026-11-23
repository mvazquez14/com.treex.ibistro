"""Pure recipe costing. Callers load rows and pass them in; this module never touches a session."""

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from uuid import UUID

from app.models.enums import PricingType

MAX_RECIPE_DEPTH = 8
_CENT = Decimal("0.01")


class CostError(ValueError):
    """A recipe, package, or extra cannot be costed."""


@dataclass(frozen=True)
class IngredientCost:
    id: UUID
    purchase_price: Decimal
    waste_factor: float
    cooking_yield_factor: float


@dataclass(frozen=True)
class RecipeLine:
    ingredient_id: UUID | None
    sub_recipe_id: UUID | None
    net_qty_per_portion: float


@dataclass(frozen=True)
class RecipeCost:
    id: UUID
    portion_size: float
    lines: tuple[RecipeLine, ...]


@dataclass(frozen=True)
class IngredientNeed:
    ingredient_id: UUID
    net_qty: float
    gross_qty: float
    cost: Decimal


@dataclass(frozen=True)
class PackageOption:
    recipe_id: UUID
    portions_per_guest: float
    extra_price_per_guest: Decimal


@dataclass(frozen=True)
class PackageGroup:
    id: UUID
    is_fixed: bool
    min_choices: int
    max_choices: int
    options: tuple[PackageOption, ...]


@dataclass(frozen=True)
class ExtraCharge:
    pricing_type: PricingType
    unit_price: Decimal
    quantity: float
    ingredient: IngredientCost | None = None
    recipe_id: UUID | None = None


@dataclass(frozen=True)
class PackageQuote:
    cogs: Decimal
    price: Decimal
    price_per_guest: Decimal
    explosion: tuple[IngredientNeed, ...]


def as_money(value: Decimal) -> Decimal:
    return value.quantize(_CENT, rounding=ROUND_HALF_UP)


def gross_quantity(
    net_qty: float,
    waste_factor: float,
    cooking_yield_factor: float,
) -> float:
    """Purchase quantity for a net amount: net / (yield * (1 - waste))."""
    return float(_gross_amount(net_qty, waste_factor, cooking_yield_factor))


def explode_recipe(
    recipe_id: UUID,
    recipes: Mapping[UUID, RecipeCost],
    ingredients: Mapping[UUID, IngredientCost],
    *,
    portions: float = 1,
) -> tuple[IngredientNeed, ...]:
    """Expand a recipe, including sub-recipes, into gross ingredient quantities."""
    if portions < 0:
        raise CostError("La cantidad de porciones no puede ser negativa")
    return _merge(
        _walk(
            recipe_id,
            recipes,
            ingredients,
            portions=portions,
            stack=(),
        )
    )


def recipe_cost(
    recipe_id: UUID,
    recipes: Mapping[UUID, RecipeCost],
    ingredients: Mapping[UUID, IngredientCost],
    *,
    portions: float = 1,
) -> Decimal:
    lines = explode_recipe(
        recipe_id,
        recipes,
        ingredients,
        portions=portions,
    )
    total = sum((line.cost for line in lines), Decimal("0"))
    return as_money(total)


def quote_package(
    *,
    guest_count: int,
    base_price_per_guest: Decimal,
    groups: Sequence[PackageGroup],
    selected_options: Mapping[UUID, Sequence[UUID]],
    recipes: Mapping[UUID, RecipeCost],
    ingredients: Mapping[UUID, IngredientCost],
    extras: Sequence[ExtraCharge] = (),
) -> PackageQuote:
    """Price a package and return the ingredient explosion ready for the Kardex."""
    if guest_count < 1:
        raise CostError("Indica al menos un invitado")
    if base_price_per_guest < 0:
        raise CostError("El precio base no puede ser negativo")

    known = {group.id: group for group in groups}
    for group_id in selected_options:
        if group_id not in known:
            raise CostError("El grupo no pertenece al paquete")

    chosen: list[PackageOption] = []
    needs: list[IngredientNeed] = []
    for group in groups:
        options = _options_for_group(group, selected_options.get(group.id, ()))
        chosen.extend(options)
        for option in options:
            needs.extend(
                explode_recipe(
                    option.recipe_id,
                    recipes,
                    ingredients,
                    portions=guest_count * option.portions_per_guest,
                )
            )

    extra_per_guest = Decimal("0")
    extra_per_unit = Decimal("0")
    for extra in extras:
        guest_part, unit_part, extra_needs = _extra_charge(
            extra,
            guest_count=guest_count,
            recipes=recipes,
            ingredients=ingredients,
        )
        extra_per_guest += guest_part
        extra_per_unit += unit_part
        needs.extend(extra_needs)

    option_extra = sum(
        (option.extra_price_per_guest for option in chosen),
        Decimal("0"),
    )
    per_guest = base_price_per_guest + option_extra + extra_per_guest
    guests = Decimal(guest_count)
    return PackageQuote(
        cogs=as_money(sum((line.cost for line in _merge(needs)), Decimal("0"))),
        price=as_money(per_guest * guests + extra_per_unit),
        price_per_guest=as_money(per_guest),
        explosion=_merge(needs),
    )


def equipment_units(guests: int, guests_per_unit: int) -> int:
    """Units required for a headcount. Preview only: nothing is reserved by date."""
    if guests < 0:
        raise CostError("El número de invitados no puede ser negativo")
    if guests_per_unit <= 0:
        raise CostError("Los invitados por unidad deben ser al menos 1")
    if guests == 0:
        return 0
    return math.ceil(guests / guests_per_unit)


def _options_for_group(
    group: PackageGroup,
    selected_ids: Sequence[UUID],
) -> tuple[PackageOption, ...]:
    if group.is_fixed:
        return group.options
    if len(selected_ids) != len(set(selected_ids)):
        raise CostError("Hay opciones repetidas en el grupo")
    allowed = {option.recipe_id: option for option in group.options}
    chosen: list[PackageOption] = []
    for recipe_id in selected_ids:
        option = allowed.get(recipe_id)
        if option is None:
            raise CostError("La receta elegida no pertenece al grupo")
        chosen.append(option)
    count = len(chosen)
    if count < group.min_choices or count > group.max_choices:
        if group.min_choices == group.max_choices:
            raise CostError(f"Elige {group.min_choices} opciones")
        raise CostError(
            f"Elige entre {group.min_choices} y {group.max_choices} opciones"
        )
    return tuple(chosen)


def _extra_charge(
    extra: ExtraCharge,
    *,
    guest_count: int,
    recipes: Mapping[UUID, RecipeCost],
    ingredients: Mapping[UUID, IngredientCost],
) -> tuple[Decimal, Decimal, tuple[IngredientNeed, ...]]:
    if extra.quantity <= 0:
        raise CostError("La cantidad del extra debe ser mayor a cero")
    if extra.unit_price < 0:
        raise CostError("El precio del extra no puede ser negativo")
    if extra.ingredient is not None and extra.recipe_id is not None:
        raise CostError("El extra no puede tener insumo y receta a la vez")

    amount = Decimal(str(extra.quantity))
    if extra.pricing_type is PricingType.PER_GUEST:
        per_guest = extra.unit_price
        scale = extra.quantity * guest_count
        per_unit = Decimal("0")
    elif extra.pricing_type is PricingType.PER_UNIT:
        per_guest = Decimal("0")
        scale = extra.quantity
        per_unit = extra.unit_price * amount
    else:
        raise CostError("El tipo de cobro del extra no es válido")

    if extra.ingredient is not None:
        return per_guest, per_unit, (_ingredient_need(extra.ingredient, scale),)
    if extra.recipe_id is not None:
        return (
            per_guest,
            per_unit,
            explode_recipe(
                extra.recipe_id,
                recipes,
                ingredients,
                portions=scale,
            ),
        )
    return per_guest, per_unit, ()


def _walk(
    recipe_id: UUID,
    recipes: Mapping[UUID, RecipeCost],
    ingredients: Mapping[UUID, IngredientCost],
    *,
    portions: float,
    stack: tuple[UUID, ...],
) -> list[IngredientNeed]:
    if recipe_id in stack:
        raise CostError("La receta contiene un ciclo")
    path = stack + (recipe_id,)
    if len(path) > MAX_RECIPE_DEPTH:
        raise CostError("La receta supera la profundidad permitida")
    recipe = recipes.get(recipe_id)
    if recipe is None:
        raise CostError("No se encontró la receta")
    if recipe.portion_size <= 0:
        raise CostError("El tamaño de porción debe ser mayor a cero")

    needs: list[IngredientNeed] = []
    for line in recipe.lines:
        if line.net_qty_per_portion < 0:
            raise CostError("La cantidad neta no puede ser negativa")
        has_ingredient = line.ingredient_id is not None
        has_sub_recipe = line.sub_recipe_id is not None
        if has_ingredient == has_sub_recipe:
            raise CostError("La línea apunta a un insumo o a una sub-receta")
        if line.ingredient_id is not None:
            ingredient = ingredients.get(line.ingredient_id)
            if ingredient is None:
                raise CostError("No se encontró el insumo")
            needs.append(
                _ingredient_need(
                    ingredient,
                    portions * line.net_qty_per_portion,
                )
            )
            continue
        assert line.sub_recipe_id is not None
        sub_recipe = recipes.get(line.sub_recipe_id)
        if sub_recipe is None:
            raise CostError("No se encontró la sub-receta")
        if sub_recipe.portion_size <= 0:
            raise CostError("El tamaño de porción debe ser mayor a cero")
        scale = line.net_qty_per_portion / sub_recipe.portion_size
        needs.extend(
            _walk(
                line.sub_recipe_id,
                recipes,
                ingredients,
                portions=portions * scale,
                stack=path,
            )
        )
    return needs


def _ingredient_need(ingredient: IngredientCost, net_qty: float) -> IngredientNeed:
    gross = _gross_amount(
        net_qty,
        ingredient.waste_factor,
        ingredient.cooking_yield_factor,
    )
    if ingredient.purchase_price < 0:
        raise CostError("El precio de compra no puede ser negativo")
    return IngredientNeed(
        ingredient_id=ingredient.id,
        net_qty=net_qty,
        gross_qty=float(gross),
        cost=gross * ingredient.purchase_price,
    )


def _gross_amount(
    net_qty: float,
    waste_factor: float,
    cooking_yield_factor: float,
) -> Decimal:
    net = Decimal(str(net_qty))
    waste = Decimal(str(waste_factor))
    yield_factor = Decimal(str(cooking_yield_factor))
    if net < 0:
        raise CostError("La cantidad neta no puede ser negativa")
    if waste < 0 or waste >= Decimal("0.95"):
        raise CostError("La merma del insumo no es válida")
    if yield_factor < Decimal("0.10") or yield_factor > Decimal("1.50"):
        raise CostError("El rendimiento del insumo no es válido")
    denominator = yield_factor * (Decimal("1") - waste)
    if denominator <= 0:
        raise CostError("La merma y el rendimiento no permiten calcular la cantidad")
    if net == 0:
        return Decimal("0")
    return net / denominator


def _merge(lines: Sequence[IngredientNeed]) -> tuple[IngredientNeed, ...]:
    totals: dict[UUID, list[Decimal | float]] = {}
    for line in lines:
        current = totals.get(line.ingredient_id)
        if current is None:
            totals[line.ingredient_id] = [line.net_qty, line.gross_qty, line.cost]
            continue
        current[0] = float(current[0]) + line.net_qty
        current[1] = float(current[1]) + line.gross_qty
        current[2] = Decimal(str(current[2])) + line.cost
    merged = [
        IngredientNeed(
            ingredient_id=ingredient_id,
            net_qty=float(values[0]),
            gross_qty=float(values[1]),
            cost=Decimal(str(values[2])),
        )
        for ingredient_id, values in totals.items()
    ]
    merged.sort(key=lambda item: str(item.ingredient_id))
    return tuple(merged)
