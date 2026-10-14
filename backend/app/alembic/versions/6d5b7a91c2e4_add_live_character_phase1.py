"""Add Phase 1 live character tables.

Revision ID: 6d5b7a91c2e4
Revises: fe56fa70289e
Create Date: 2026-10-12
"""

from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes

revision = "6d5b7a91c2e4"
down_revision = "fe56fa70289e"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "character",
        sa.Column("name", sqlmodel.sql.sqltypes.AutoString(length=80), nullable=False),
        sa.Column("template_id", sqlmodel.sql.sqltypes.AutoString(length=50), nullable=False),
        sa.Column("persona_description", sqlmodel.sql.sqltypes.AutoString(length=1200), nullable=False),
        sa.Column("address_streamer_as", sqlmodel.sql.sqltypes.AutoString(length=40), nullable=False),
        sa.Column("viewer_style", sqlmodel.sql.sqltypes.AutoString(length=120), nullable=False),
        sa.Column("humor_level", sqlmodel.sql.sqltypes.AutoString(length=20), nullable=False),
        sa.Column("proactivity", sqlmodel.sql.sqltypes.AutoString(length=20), nullable=False),
        sa.Column("voice_provider", sqlmodel.sql.sqltypes.AutoString(length=30), nullable=False),
        sa.Column("voice_id", sqlmodel.sql.sqltypes.AutoString(length=80), nullable=False),
        sa.Column("avatar_asset_id", sqlmodel.sql.sqltypes.AutoString(length=255), nullable=True),
        sa.Column("memory_opt_in", sa.Boolean(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["owner_id"], ["user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_character_owner_id"), "character", ["owner_id"])
    op.create_table(
        "livesession",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("character_id", sa.Uuid(), nullable=False),
        sa.Column("mode", sqlmodel.sql.sqltypes.AutoString(length=20), nullable=False),
        sa.Column("status", sqlmodel.sql.sqltypes.AutoString(length=20), nullable=False),
        sa.Column("ai_muted", sa.Boolean(), nullable=False),
        sa.Column("mic_connected", sa.Boolean(), nullable=False),
        sa.Column("session_epoch", sa.Integer(), nullable=False),
        sa.Column("overlay_key_hash", sqlmodel.sql.sqltypes.AutoString(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("stopped_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["character_id"], ["character.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["owner_id"], ["user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_livesession_character_id"), "livesession", ["character_id"])
    op.create_index(op.f("ix_livesession_owner_id"), "livesession", ["owner_id"])
    op.create_index(op.f("ix_livesession_status"), "livesession", ["status"])
    op.create_index(
        "uq_one_active_session_per_user",
        "livesession",
        ["owner_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('active', 'paused')"),
    )
    op.create_table(
        "paidevent",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("live_session_id", sa.Uuid(), nullable=False),
        sa.Column("provider_event_id", sqlmodel.sql.sqltypes.AutoString(length=255), nullable=False),
        sa.Column("event_type", sqlmodel.sql.sqltypes.AutoString(length=40), nullable=False),
        sa.Column("author_display_name", sqlmodel.sql.sqltypes.AutoString(length=255), nullable=False),
        sa.Column("amount_micros", sa.BigInteger(), nullable=False),
        sa.Column("currency", sqlmodel.sql.sqltypes.AutoString(length=3), nullable=False),
        sa.Column("ack_status", sqlmodel.sql.sqltypes.AutoString(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["live_session_id"], ["livesession.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("live_session_id", "provider_event_id", name="uq_paid_event_provider"),
    )
    op.create_index(op.f("ix_paidevent_live_session_id"), "paidevent", ["live_session_id"])
    op.create_index(op.f("ix_paidevent_provider_event_id"), "paidevent", ["provider_event_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_paidevent_provider_event_id"), table_name="paidevent")
    op.drop_index(op.f("ix_paidevent_live_session_id"), table_name="paidevent")
    op.drop_table("paidevent")
    op.drop_index("uq_one_active_session_per_user", table_name="livesession")
    op.drop_index(op.f("ix_livesession_status"), table_name="livesession")
    op.drop_index(op.f("ix_livesession_owner_id"), table_name="livesession")
    op.drop_index(op.f("ix_livesession_character_id"), table_name="livesession")
    op.drop_table("livesession")
    op.drop_index(op.f("ix_character_owner_id"), table_name="character")
    op.drop_table("character")
