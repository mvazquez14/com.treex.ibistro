"""Store a before-and-after log on each reservation edit."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "f8c3d7a26b51"
down_revision = "e7a1b5d04e39"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("reservation")}
    if "change_log" not in columns:
        op.add_column(
            "reservation",
            sa.Column(
                "change_log",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=False,
                server_default=sa.text("'[]'::jsonb"),
            ),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("reservation")}
    if "change_log" in columns:
        op.drop_column("reservation", "change_log")
