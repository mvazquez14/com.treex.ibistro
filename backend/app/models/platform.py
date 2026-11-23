"""Platform governance records. Not a tenant operational table."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Column, String
from sqlmodel import Field, SQLModel

from app.models.columns import created_at_column, jsonb_column, utcnow, uuid_pk


class PlatformAuditLog(SQLModel, table=True):
    __tablename__ = "platform_audit_log"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, sa_column=uuid_pk())
    actor_nuna_org_id: str = Field(sa_column=Column(String(128), nullable=False))
    actor_email: str = Field(default="", sa_column=Column(String(255), nullable=False))
    action: str = Field(sa_column=Column(String(80), nullable=False))
    target_tenant_id: uuid.UUID | None = Field(default=None)
    detail: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=jsonb_column("'{}'::jsonb"),
    )
    created_at: datetime = Field(default_factory=utcnow, sa_column=created_at_column())
