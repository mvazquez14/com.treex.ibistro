"""Add onboarding state and partial uniqueness for RFC and WhatsApp.

Existing providers are marked complete so a deploy does not trap them in
the wizard. New rows stay incomplete until /onboarding/complete.
"""

import sqlalchemy as sa
from alembic import op

revision = "b7e1c4a92d10"
down_revision = "a91c4e2b80d1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    columns = {column["name"] for column in sa.inspect(bind).get_columns("tenant")}
    if "onboarding_completed" not in columns:
        op.add_column(
            "tenant",
            sa.Column(
                "onboarding_completed",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            ),
        )
        op.execute("UPDATE tenant SET onboarding_completed = true")
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_tenant_rfc_present "
        "ON tenant (rfc) WHERE rfc <> ''"
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_tenant_whatsapp_present "
        "ON tenant (whatsapp_phone) WHERE whatsapp_phone <> ''"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_tenant_whatsapp_present")
    op.execute("DROP INDEX IF EXISTS uq_tenant_rfc_present")
    op.drop_column("tenant", "onboarding_completed")
