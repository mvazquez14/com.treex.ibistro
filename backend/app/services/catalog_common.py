"""Shared checks for the menu, warehouse, and equipment catalogs."""

import re
from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum
from uuid import UUID

from fastapi import HTTPException, status
from sqlmodel.ext.asyncio.session import AsyncSession

_E164 = re.compile(r"^\+[1-9]\d{7,14}$")
_CENT = Decimal("0.01")


def clean_name(value: str, *, limit: int = 255) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Indica el nombre",
        )
    if len(cleaned) > limit:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="El nombre es demasiado largo",
        )
    return cleaned


def clean_text(value: str | None, *, limit: int = 2000) -> str:
    cleaned = (value or "").strip()
    if len(cleaned) > limit:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="El texto es demasiado largo",
        )
    return cleaned


def clean_optional(value: str | None, *, limit: int) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    if not cleaned:
        return None
    if len(cleaned) > limit:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="El texto es demasiado largo",
        )
    return cleaned


def clean_money(value: Decimal, label: str) -> Decimal:
    if value < 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"{label} no puede ser negativo",
        )
    return value.quantize(_CENT, rounding=ROUND_HALF_UP)


def clean_phone(value: str | None) -> str:
    cleaned = (value or "").strip()
    if not cleaned:
        return ""
    if _E164.fullmatch(cleaned) is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=(
                "El teléfono debe estar en formato internacional, "
                "por ejemplo +523312345678"
            ),
        )
    return cleaned


def clean_email(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    if not cleaned:
        return None
    if "@" not in cleaned or cleaned.startswith("@") or cleaned.endswith("@"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="El correo no es válido",
        )
    if len(cleaned) > 255:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="El correo es demasiado largo",
        )
    return cleaned


def as_enum[E: StrEnum](enum_cls: type[E], value: str, message: str) -> E:
    try:
        return enum_cls(value)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=message,
        )


def require_portion(value: float, message: str) -> float:
    if value <= 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=message,
        )
    return value


async def owned[T](
    session: AsyncSession,
    model: type[T],
    object_id: UUID,
    tenant_id: UUID,
    message: str,
) -> T:
    row = await session.get(model, object_id)
    if row is None or getattr(row, "tenant_id", None) != tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=message)
    return row


def conflict(message: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=message)
