from decimal import Decimal, InvalidOperation
from uuid import UUID

from fastapi import HTTPException, status


def optional_uuid(value: str | None) -> UUID | None:
    if value is None or not value.strip():
        return None
    try:
        return UUID(value.strip())
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="El identificador no es válido",
        )


def decimal_field(value: str, label: str) -> Decimal:
    try:
        return Decimal(value.strip())
    except InvalidOperation, AttributeError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"{label} debe ser un número",
        )


def optional_decimal(value: str | None, label: str) -> Decimal | None:
    if value is None or not value.strip():
        return None
    return decimal_field(value, label)


def float_field(value: str, label: str) -> float:
    try:
        return float(value.strip())
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"{label} debe ser un número",
        )


def int_field(value: str, label: str) -> int:
    try:
        return int(value.strip())
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"{label} debe ser un número entero",
        )


def checked(value: str | None) -> bool:
    return value in {"true", "on", "1", "yes"}
