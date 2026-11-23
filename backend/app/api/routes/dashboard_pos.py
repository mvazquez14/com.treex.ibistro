"""HTMX counter for on-site sales."""

from collections.abc import Awaitable, Callable

from fastapi import APIRouter, HTTPException, Request, status
from starlette.datastructures import FormData
from starlette.responses import Response

from app.api.deps import CurrentActiveTenant, SessionDep
from app.api.forms import checked, decimal_field, optional_uuid
from app.schemas.operations import PosLineIn, PosSaleIn
from app.services import pos
from app.services.reservations import parse_method
from app.templating import failure, render

router = APIRouter(prefix="/pos", tags=["dashboard"])


async def _render(
    request: Request,
    session: SessionDep,
    tenant: CurrentActiveTenant,
    error: str | None = None,
    status_code: int = 200,
) -> Response:
    screen = await pos.pos_screen(session, tenant)
    return render(
        request,
        "dashboard/pos.html",
        "dashboard/pos_panel.html",
        {"section": "pos", "screen": screen, "error": error},
        status_code,
    )


async def _run(
    request: Request,
    session: SessionDep,
    tenant: CurrentActiveTenant,
    action: Callable[[], Awaitable[None]],
) -> Response:
    try:
        await action()
        await session.commit()
    except HTTPException as exc:
        await session.rollback()
        message, code = failure(exc)
        return await _render(request, session, tenant, message, code)
    return await _render(request, session, tenant)


@router.get("")
async def pos_page(
    request: Request, session: SessionDep, tenant: CurrentActiveTenant
) -> Response:
    return await _render(request, session, tenant)


@router.post("/sales")
async def create_sale(
    request: Request, session: SessionDep, tenant: CurrentActiveTenant
) -> Response:
    form = await request.form()

    async def action() -> None:
        await pos.checkout(session, tenant, _sale_from_form(form))

    return await _run(request, session, tenant, action)


def _sale_from_form(form: FormData) -> PosSaleIn:
    warehouse_id = optional_uuid(_text(form.get("warehouse_id")))
    if warehouse_id is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Elige un almacén",
        )
    tax_rate = _text(form.get("tax_rate"))
    reservation_id = optional_uuid(_text(form.get("reservation_id")))
    return PosSaleIn(
        warehouse_id=warehouse_id,
        payment_method=parse_method(_text(form.get("payment_method"))),
        apply_tax=checked(_text(form.get("apply_tax"))),
        tax_rate=decimal_field(tax_rate, "La tasa de IVA") if tax_rate else None,
        reservation_id=reservation_id,
        lines=_lines(form),
    )


def _lines(form: FormData) -> list[PosLineIn]:
    lines: list[PosLineIn] = []
    for key, value in form.multi_items():
        if not isinstance(value, str) or not key.startswith("qty_"):
            continue
        text = value.strip()
        if not text:
            continue
        try:
            quantity = float(text)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="La cantidad debe ser un número",
            )
        if quantity <= 0:
            continue
        kind = _text(form.get(f"kind_{key.removeprefix('qty_')}"))
        item_id = optional_uuid(key.removeprefix("qty_"))
        if item_id is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="El producto no es válido",
            )
        if kind == "ingredient":
            lines.append(
                PosLineIn(kind="ingredient", item_id=item_id, quantity=quantity)
            )
        elif kind == "extra":
            lines.append(PosLineIn(kind="extra", item_id=item_id, quantity=quantity))
        elif kind == "package":
            lines.append(PosLineIn(kind="package", item_id=item_id, quantity=quantity))
        else:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="El producto no es válido",
            )
    return lines


def _text(value: object) -> str:
    return value if isinstance(value, str) else ""
