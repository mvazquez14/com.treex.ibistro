"""Add the platform audit log.

Databases that already applied the first revision get the new table.
A fresh install already created it inside that revision's create_all,
so running create_all again only fills what is missing.
"""

from alembic import op

from app.models import SQLModel

revision = "a91c4e2b80d1"
down_revision = "c3a8e1b74f02"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    SQLModel.metadata.create_all(bind)


def downgrade() -> None:
    op.drop_table("platform_audit_log")
