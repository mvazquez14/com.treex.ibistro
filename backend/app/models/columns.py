import uuid
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import Column, DateTime, ForeignKey, Numeric, Text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.sql import text
from sqlmodel import SQLModel

_ENUMS: dict[str, SAEnum] = {}


def utcnow() -> datetime:
    return datetime.now(UTC)


def uuid_pk() -> Any:
    return Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


def fk(
    target: str,
    *,
    ondelete: str = "CASCADE",
    nullable: bool = False,
    unique: bool = False,
    index: bool = True,
) -> Any:
    return Column(
        UUID(as_uuid=True),
        ForeignKey(target, ondelete=ondelete),
        nullable=nullable,
        unique=unique,
        index=index,
    )


def enum_column(enum_cls: type[StrEnum], name: str, *, nullable: bool = False) -> Any:
    enum_type = _ENUMS.get(name)
    if enum_type is None:
        enum_type = SAEnum(
            enum_cls,
            name=name,
            native_enum=True,
            metadata=SQLModel.metadata,
            values_callable=lambda members: [member.value for member in members],
        )
        _ENUMS[name] = enum_type
    return Column(enum_type, nullable=nullable)


def money_column(*, nullable: bool = False) -> Any:
    default = None if nullable else text("0")
    return Column(Numeric(12, 2), nullable=nullable, server_default=default)


def jsonb_column(server_default: str) -> Any:
    return Column(
        JSONB,
        nullable=False,
        server_default=text(server_default),
    )


def text_column(*, nullable: bool = False) -> Any:
    if nullable:
        return Column(Text, nullable=True)
    return Column(Text, nullable=False, server_default=text("''"))


def created_at_column() -> Any:
    return Column(DateTime(timezone=True), nullable=False)
