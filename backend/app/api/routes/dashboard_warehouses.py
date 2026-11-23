from collections.abc import Awaitable, Callable
from uuid import UUID

from fastapi import APIRouter, Form, HTTPException, Request
from starlette.responses import Response

from app.api.deps import CurrentActiveTenant, SessionDep
from app.api.forms import (
    checked,
    decimal_field,
    float_field,
    optional_decimal,
    optional_uuid,
)
from app.schemas.catalog import (
    IngredientIn,
    IngredientUpdate,
    MovementIn,
    SupplierIn,
    SupplierUpdate,
    WarehouseIn,
    WarehouseUpdate,
)
from app.services import warehouse_catalog as catalog
from app.templating import failure, render

router = APIRouter(prefix="/warehouses", tags=["dashboard"])


async def _render(
    request: Request,
    session: SessionDep,
    tenant_id: UUID,
    error: str | None = None,
    status_code: int = 200,
    warehouse_id: UUID | None = None,
    ingredient_id: UUID | None = None,
) -> Response:
    try:
        snapshot = await catalog.warehouse_snapshot(
            session,
            tenant_id,
            warehouse_id=warehouse_id,
            ingredient_id=ingredient_id,
        )
    except HTTPException as exc:
        message, code = failure(exc)
        snapshot = await catalog.warehouse_snapshot(session, tenant_id)
        error = message if error is None else error
        status_code = code
    return render(
        request,
        "dashboard/warehouses.html",
        "dashboard/warehouses_panel.html",
        {
            "section": "warehouses",
            "snapshot": snapshot,
            "error": error,
            "warehouse_id": warehouse_id,
            "ingredient_id": ingredient_id,
        },
        status_code,
    )


async def _run(
    request: Request,
    session: SessionDep,
    tenant: CurrentActiveTenant,
    action: Callable[[], Awaitable[None]],
) -> Response:
    tenant_id = tenant.id
    try:
        await action()
        await session.commit()
    except HTTPException as exc:
        await session.rollback()
        message, code = failure(exc)
        return await _render(request, session, tenant_id, message, code)
    return await _render(request, session, tenant_id)


@router.get("")
async def warehouses_page(
    request: Request,
    session: SessionDep,
    tenant: CurrentActiveTenant,
    warehouse_id: str | None = None,
    ingredient_id: str | None = None,
) -> Response:
    try:
        warehouse = optional_uuid(warehouse_id)
        ingredient = optional_uuid(ingredient_id)
    except HTTPException as exc:
        message, code = failure(exc)
        return await _render(request, session, tenant.id, message, code)
    return await _render(
        request,
        session,
        tenant.id,
        warehouse_id=warehouse,
        ingredient_id=ingredient,
    )


@router.post("/suppliers")
async def create_supplier(
    request: Request,
    session: SessionDep,
    tenant: CurrentActiveTenant,
    name: str = Form(),
    contact_name: str = Form(default=""),
    phone: str = Form(default=""),
    email: str = Form(default=""),
    notes: str = Form(default=""),
) -> Response:
    async def action() -> None:
        await catalog.create_supplier(
            session,
            tenant.id,
            SupplierIn(
                name=name,
                contact_name=contact_name,
                phone=phone,
                email=email or None,
                notes=notes or None,
            ),
        )

    return await _run(request, session, tenant, action)


@router.post("/suppliers/{supplier_id}")
async def update_supplier(
    request: Request,
    session: SessionDep,
    tenant: CurrentActiveTenant,
    supplier_id: UUID,
    name: str = Form(),
    contact_name: str = Form(default=""),
    phone: str = Form(default=""),
    email: str = Form(default=""),
    notes: str = Form(default=""),
) -> Response:
    async def action() -> None:
        await catalog.update_supplier(
            session,
            tenant.id,
            supplier_id,
            SupplierUpdate(
                name=name,
                contact_name=contact_name,
                phone=phone,
                email=email or None,
                notes=notes or None,
            ),
        )

    return await _run(request, session, tenant, action)


@router.post("/suppliers/{supplier_id}/delete")
async def remove_supplier(
    request: Request,
    session: SessionDep,
    tenant: CurrentActiveTenant,
    supplier_id: UUID,
) -> Response:
    async def action() -> None:
        await catalog.delete_supplier(session, tenant.id, supplier_id)

    return await _run(request, session, tenant, action)


@router.post("/sites")
async def create_warehouse(
    request: Request,
    session: SessionDep,
    tenant: CurrentActiveTenant,
    name: str = Form(),
    location_notes: str = Form(default=""),
    is_primary: str | None = Form(default=None),
) -> Response:
    async def action() -> None:
        await catalog.create_warehouse(
            session,
            tenant.id,
            WarehouseIn(
                name=name,
                location_notes=location_notes or None,
                is_primary=checked(is_primary),
            ),
        )

    return await _run(request, session, tenant, action)


@router.post("/sites/{warehouse_id}")
async def update_warehouse(
    request: Request,
    session: SessionDep,
    tenant: CurrentActiveTenant,
    warehouse_id: UUID,
    name: str = Form(),
    location_notes: str = Form(default=""),
    is_primary: str | None = Form(default=None),
) -> Response:
    async def action() -> None:
        await catalog.update_warehouse(
            session,
            tenant.id,
            warehouse_id,
            WarehouseUpdate(
                name=name,
                location_notes=location_notes or None,
                is_primary=checked(is_primary),
            ),
        )

    return await _run(request, session, tenant, action)


@router.post("/sites/{warehouse_id}/delete")
async def remove_warehouse(
    request: Request,
    session: SessionDep,
    tenant: CurrentActiveTenant,
    warehouse_id: UUID,
) -> Response:
    async def action() -> None:
        await catalog.delete_warehouse(session, tenant.id, warehouse_id)

    return await _run(request, session, tenant, action)


@router.post("/ingredients")
async def create_ingredient(
    request: Request,
    session: SessionDep,
    tenant: CurrentActiveTenant,
    name: str = Form(),
    unit: str = Form(),
    purchase_price: str = Form(),
    sale_price: str = Form(default=""),
    min_stock: str = Form(default="0"),
    max_stock: str = Form(default="0"),
    waste_factor: str = Form(default="0"),
    cooking_yield_factor: str = Form(default="1"),
    supplier_id: str = Form(default=""),
) -> Response:
    async def action() -> None:
        await catalog.create_ingredient(
            session,
            tenant.id,
            IngredientIn(
                name=name,
                unit=catalog.parse_unit(unit),
                purchase_price=decimal_field(purchase_price, "El precio de compra"),
                sale_price=optional_decimal(sale_price, "El precio de venta"),
                min_stock=float_field(min_stock, "El stock mínimo"),
                max_stock=float_field(max_stock, "El stock máximo"),
                waste_factor=float_field(waste_factor, "La merma"),
                cooking_yield_factor=float_field(
                    cooking_yield_factor, "El rendimiento"
                ),
                supplier_id=optional_uuid(supplier_id),
            ),
        )

    return await _run(request, session, tenant, action)


@router.post("/ingredients/{ingredient_id}")
async def update_ingredient(
    request: Request,
    session: SessionDep,
    tenant: CurrentActiveTenant,
    ingredient_id: UUID,
    name: str = Form(),
    unit: str = Form(),
    purchase_price: str = Form(),
    sale_price: str = Form(default=""),
    min_stock: str = Form(default="0"),
    max_stock: str = Form(default="0"),
    waste_factor: str = Form(default="0"),
    cooking_yield_factor: str = Form(default="1"),
    supplier_id: str = Form(default=""),
) -> Response:
    async def action() -> None:
        supplier = optional_uuid(supplier_id)
        price = optional_decimal(sale_price, "El precio de venta")
        await catalog.update_ingredient(
            session,
            tenant.id,
            ingredient_id,
            IngredientUpdate(
                name=name,
                unit=catalog.parse_unit(unit),
                purchase_price=decimal_field(purchase_price, "El precio de compra"),
                sale_price=price,
                clear_sale_price=price is None,
                min_stock=float_field(min_stock, "El stock mínimo"),
                max_stock=float_field(max_stock, "El stock máximo"),
                waste_factor=float_field(waste_factor, "La merma"),
                cooking_yield_factor=float_field(
                    cooking_yield_factor, "El rendimiento"
                ),
                supplier_id=supplier,
                clear_supplier=supplier is None,
            ),
        )

    return await _run(request, session, tenant, action)


@router.post("/ingredients/{ingredient_id}/delete")
async def remove_ingredient(
    request: Request,
    session: SessionDep,
    tenant: CurrentActiveTenant,
    ingredient_id: UUID,
) -> Response:
    async def action() -> None:
        await catalog.delete_ingredient(session, tenant.id, ingredient_id)

    return await _run(request, session, tenant, action)


@router.post("/movements")
async def create_movement(
    request: Request,
    session: SessionDep,
    tenant: CurrentActiveTenant,
    warehouse_id: str = Form(),
    ingredient_id: str = Form(),
    movement_type: str = Form(),
    quantity: str = Form(),
) -> Response:
    async def action() -> None:
        warehouse = optional_uuid(warehouse_id)
        ingredient = optional_uuid(ingredient_id)
        if warehouse is None or ingredient is None:
            raise HTTPException(status_code=422, detail="Elige el almacén y el insumo")
        await catalog.record_movement(
            session,
            tenant.id,
            MovementIn(
                warehouse_id=warehouse,
                ingredient_id=ingredient,
                movement_type=catalog.parse_movement(movement_type),
                quantity=float_field(quantity, "La cantidad"),
            ),
        )

    return await _run(request, session, tenant, action)
