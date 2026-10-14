"""Add the Phase 3 per-session voice provider mode.

Revision ID: c4a7e2b913d1
Revises: b2f14b7ca902
Create Date: 2026-10-12
"""

import sqlalchemy as sa
import sqlmodel.sql.sqltypes
from alembic import op

revision = "c4a7e2b913d1"
down_revision = "b2f14b7ca902"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "livesession",
        sa.Column(
            "voice_mode",
            sqlmodel.sql.sqltypes.AutoString(length=20),
            nullable=False,
            server_default="mock",
        ),
    )


def downgrade() -> None:
    op.drop_column("livesession", "voice_mode")
