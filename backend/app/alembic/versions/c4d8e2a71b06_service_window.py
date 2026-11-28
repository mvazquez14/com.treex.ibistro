"""Store the on-site service duration and the booked start time."""

import sqlalchemy as sa
from alembic import op

revision = "c4d8e2a71b06"
down_revision = "b7e1c4a92d10"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    tenant_columns = {column["name"] for column in sa.inspect(bind).get_columns("tenant")}
    if "service_duration_minutes" not in tenant_columns:
        op.add_column(
            "tenant",
            sa.Column(
                "service_duration_minutes",
                sa.Integer(),
                nullable=False,
                server_default="120",
            ),
        )
    quote_columns = {column["name"] for column in sa.inspect(bind).get_columns("quote")}
    if "event_start" not in quote_columns:
        op.add_column("quote", sa.Column("event_start", sa.Time(), nullable=True))
    reservation_columns = {
        column["name"] for column in sa.inspect(bind).get_columns("reservation")
    }
    if "event_start" not in reservation_columns:
        op.add_column("reservation", sa.Column("event_start", sa.Time(), nullable=True))


def downgrade() -> None:
    op.drop_column("reservation", "event_start")
    op.drop_column("quote", "event_start")
    op.drop_column("tenant", "service_duration_minutes")
