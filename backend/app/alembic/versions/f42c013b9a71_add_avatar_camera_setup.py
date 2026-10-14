"""Persist per-character avatar framing and zoom."""

import sqlalchemy as sa
from alembic import op

revision = "f42c013b9a71"
down_revision = "ea2f6a419c04"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "character",
        sa.Column(
            "avatar_camera_framing",
            sa.String(length=20),
            nullable=False,
            server_default="chest-up",
        ),
    )
    op.add_column(
        "character",
        sa.Column(
            "avatar_camera_zoom",
            sa.Float(),
            nullable=False,
            server_default="1.0",
        ),
    )


def downgrade() -> None:
    op.drop_column("character", "avatar_camera_zoom")
    op.drop_column("character", "avatar_camera_framing")
