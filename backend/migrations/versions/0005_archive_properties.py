"""Store property archival timestamps."""

import sqlalchemy as sa
from alembic import op

revision = "0005_archive_properties"
down_revision = "0004_ml_inferences"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("properties", sa.Column("archived_at", sa.DateTime(timezone=True)))


def downgrade() -> None:
    op.drop_column("properties", "archived_at")
