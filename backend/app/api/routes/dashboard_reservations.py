"""HTMX reservation desk."""

from collections.abc import Awaitable, Callable
from uuid import UUID

from fastapi import APIRouter, Form, HTTPException, Request
from starlette.responses import Response

from app.api.deps import CurrentActiveTenant, SessionDep
from app.api.forms import checked, decimal_field
from app.schemas.operations import ReceiptIn
from app.services import reservations
from app.templating import failure, render

router = APIRouter(prefix="/reservations", tags=["dashboard"])


async def _render(
    request: Request,
    session: SessionDep,
    tenant: CurrentActiveTenant,
    error: str | None = None,
    status_code: int = 200,
) -> Response:
    screen = await reservations.reservations_screen(session, tenant.id)
    return render(
        request,
        "dashboard/reservations.html",
        "dashboard/reservations_panel.html",
        {"section": "reservations", "screen": screen, "error": error},
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
async def reservations_page(
    request: Request, session: SessionDep, tenant: CurrentActiveTenant
) -> Response:
    return await _render(request, session, tenant)


@router.post("/{reservation_id}/receipts")
async def create_receipt(
    request: Request,
    session: SessionDep,
    tenant: CurrentActiveTenant,
    reservation_id: UUID,
    amount: str = Form(),
    payment_method: str = Form(),
    receipt_file_url: str = Form(default=""),
    is_verified: str = Form(default=""),
) -> Response:
    async def action() -> None:
        data = ReceiptIn(
            amount=decimal_field(amount, "El abono"),
            payment_method=reservations.parse_method(payment_method),
            receipt_file_url=receipt_file_url or None,
            is_verified=checked(is_verified),
        )
        await reservations.add_receipt(session, tenant.id, reservation_id, data)

    return await _run(request, session, tenant, action)


@router.post("/{reservation_id}/receipts/{receipt_id}/verify")
async def verify_receipt(
    request: Request,
    session: SessionDep,
    tenant: CurrentActiveTenant,
    reservation_id: UUID,
    receipt_id: UUID,
) -> Response:
    async def action() -> None:
        await reservations.verify_receipt(
            session, tenant.id, reservation_id, receipt_id
        )

    return await _run(request, session, tenant, action)


@router.post("/{reservation_id}/receipts/{receipt_id}/delete")
async def delete_receipt(
    request: Request,
    session: SessionDep,
    tenant: CurrentActiveTenant,
    reservation_id: UUID,
    receipt_id: UUID,
) -> Response:
    async def action() -> None:
        await reservations.delete_receipt(
            session, tenant.id, reservation_id, receipt_id
        )

    return await _run(request, session, tenant, action)


@router.post("/{reservation_id}/prepare")
async def prepare_reservation(
    request: Request,
    session: SessionDep,
    tenant: CurrentActiveTenant,
    reservation_id: UUID,
) -> Response:
    async def action() -> None:
        await reservations.start_prep(session, tenant.id, reservation_id)

    return await _run(request, session, tenant, action)


@router.post("/{reservation_id}/close")
async def close_reservation(
    request: Request,
    session: SessionDep,
    tenant: CurrentActiveTenant,
    reservation_id: UUID,
) -> Response:
    async def action() -> None:
        await reservations.close_reservation(session, tenant.id, reservation_id)

    return await _run(request, session, tenant, action)


@router.post("/{reservation_id}/cancel")
async def cancel_reservation(
    request: Request,
    session: SessionDep,
    tenant: CurrentActiveTenant,
    reservation_id: UUID,
) -> Response:
    async def action() -> None:
        await reservations.cancel_reservation(session, tenant.id, reservation_id)

    return await _run(request, session, tenant, action)
