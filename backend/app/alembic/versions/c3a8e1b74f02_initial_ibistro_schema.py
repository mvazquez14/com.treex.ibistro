"""Initial iBistro schema.

The model metadata is the source of the tables. This revision is the only
one in the tree; the template user/item history was discarded.
"""

from alembic import op

from app.models import SQLModel

revision = "c3a8e1b74f02"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    SQLModel.metadata.create_all(bind)


def downgrade() -> None:
    bind = op.get_bind()
    SQLModel.metadata.drop_all(bind)
