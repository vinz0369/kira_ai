"""Add per-character LLM provider and model selection.

Revision ID: ea2f6a419c04
Revises: c4a7e2b913d1
Create Date: 2026-10-14
"""

import sqlalchemy as sa
import sqlmodel.sql.sqltypes
from alembic import op

revision = "ea2f6a419c04"
down_revision = "c4a7e2b913d1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "character",
        sa.Column(
            "llm_provider",
            sqlmodel.sql.sqltypes.AutoString(length=30),
            nullable=False,
            server_default="openai",
        ),
    )
    op.add_column(
        "character",
        sa.Column(
            "llm_model",
            sqlmodel.sql.sqltypes.AutoString(length=120),
            nullable=False,
            server_default="gpt-5.4-mini",
        ),
    )


def downgrade() -> None:
    op.drop_column("character", "llm_model")
    op.drop_column("character", "llm_provider")
