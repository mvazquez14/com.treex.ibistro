from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any

from fastapi import HTTPException
from starlette.requests import Request
from starlette.responses import Response
from starlette.templating import Jinja2Templates

from app.core.config import settings
from app.services.impersonation import impersonated_name

templates = Jinja2Templates(
    directory=str(Path(__file__).resolve().parent / "templates")
)


def pesos(value: object) -> str:
    if value is None or value == "":
        return "—"
    amount = Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return f"${amount:,.2f}"


def cantidad(value: object) -> str:
    if value is None or value == "":
        return "—"
    number = Decimal(str(value))
    text = format(number, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


templates.env.filters["pesos"] = pesos
templates.env.filters["cantidad"] = cantidad


def render(
    request: Request,
    page: str,
    partial: str,
    context: dict[str, Any],
    status_code: int = 200,
) -> Response:
    payload = dict(context)
    payload.setdefault("impersonating", impersonated_name(request))
    payload.setdefault("billing_url", settings.NUNA_BILLING_URL)
    name = partial if request.headers.get("hx-request") else page
    return templates.TemplateResponse(request, name, payload, status_code=status_code)


def failure(exc: HTTPException) -> tuple[str, int]:
    detail = exc.detail
    if isinstance(detail, dict):
        message = detail.get("message", "No se pudo completar la operación")
        return str(message), exc.status_code
    return str(detail), exc.status_code
