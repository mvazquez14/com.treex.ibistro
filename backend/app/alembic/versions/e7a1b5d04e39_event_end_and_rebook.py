"""Store the booked end time and allow another reservation on a quote."""

import sqlalchemy as sa
from alembic import op

revision = "e7a1b5d04e39"
down_revision = "d5e9f3b82c17"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    quote_columns = {column["name"] for column in inspector.get_columns("quote")}
    reservation_columns = {
        column["name"] for column in inspector.get_columns("reservation")
    }
    if "end_time" not in quote_columns:
        op.add_column("quote", sa.Column("end_time", sa.Time(), nullable=True))
    if "end_time" not in reservation_columns:
        op.add_column("reservation", sa.Column("end_time", sa.Time(), nullable=True))
    unique_names = {
        item["name"]
        for item in inspector.get_unique_constraints("reservation")
        if item.get("name")
    }
    if "reservation_quote_id_key" in unique_names:
        op.drop_constraint("reservation_quote_id_key", "reservation", type_="unique")


def downgrade() -> None:
    op.create_unique_constraint(
        "reservation_quote_id_key", "reservation", ["quote_id"]
    )
    op.drop_column("reservation", "end_time")
    op.drop_column("quote", "end_time")
