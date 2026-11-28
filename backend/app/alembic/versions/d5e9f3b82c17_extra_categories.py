"""Link each extra to the service categories where it can be offered."""

import sqlalchemy as sa
from alembic import op

revision = "d5e9f3b82c17"
down_revision = "c4d8e2a71b06"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if sa.inspect(bind).has_table("extra_category"):
        return
    op.create_table(
        "extra_category",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("extra_id", sa.Uuid(), nullable=False),
        sa.Column("category_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["extra_id"], ["menu_extra.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["category_id"], ["service_category.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("extra_id", "category_id", name="uq_extra_category"),
    )
    op.create_index("ix_extra_category_tenant_id", "extra_category", ["tenant_id"])
    op.create_index("ix_extra_category_extra_id", "extra_category", ["extra_id"])
    op.create_index("ix_extra_category_category_id", "extra_category", ["category_id"])


def downgrade() -> None:
    op.drop_index("ix_extra_category_category_id", table_name="extra_category")
    op.drop_index("ix_extra_category_extra_id", table_name="extra_category")
    op.drop_index("ix_extra_category_tenant_id", table_name="extra_category")
    op.drop_table("extra_category")
