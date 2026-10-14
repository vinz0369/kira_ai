"""Add Phase 2 YouTube OAuth and ingestion state.

Revision ID: b2f14b7ca902
Revises: 6d5b7a91c2e4
Create Date: 2026-10-12
"""

import sqlalchemy as sa
import sqlmodel.sql.sqltypes
from alembic import op

revision = "b2f14b7ca902"
down_revision = "6d5b7a91c2e4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "livesession",
        sa.Column(
            "youtube_broadcast_id",
            sqlmodel.sql.sqltypes.AutoString(length=255),
            nullable=True,
        ),
    )
    op.add_column(
        "livesession",
        sa.Column(
            "youtube_live_chat_id",
            sqlmodel.sql.sqltypes.AutoString(length=255),
            nullable=True,
        ),
    )
    op.add_column(
        "livesession",
        sa.Column("youtube_next_page_token", sa.Text(), nullable=True),
    )
    op.add_column(
        "livesession",
        sa.Column(
            "youtube_ingest_status",
            sqlmodel.sql.sqltypes.AutoString(length=30),
            nullable=False,
            server_default="disabled",
        ),
    )
    op.add_column(
        "livesession",
        sa.Column(
            "youtube_last_error",
            sqlmodel.sql.sqltypes.AutoString(length=80),
            nullable=True,
        ),
    )
    op.add_column(
        "livesession",
        sa.Column("youtube_connected_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        op.f("ix_livesession_youtube_broadcast_id"),
        "livesession",
        ["youtube_broadcast_id"],
    )

    op.create_table(
        "oauthconnection",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column(
            "provider",
            sqlmodel.sql.sqltypes.AutoString(length=40),
            nullable=False,
        ),
        sa.Column("encrypted_access_token", sa.Text(), nullable=False),
        sa.Column("encrypted_refresh_token", sa.Text(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "granted_scopes",
            sqlmodel.sql.sqltypes.AutoString(length=1024),
            nullable=False,
        ),
        sa.Column(
            "provider_channel_id",
            sqlmodel.sql.sqltypes.AutoString(length=255),
            nullable=True,
        ),
        sa.Column(
            "provider_channel_name",
            sqlmodel.sql.sqltypes.AutoString(length=255),
            nullable=True,
        ),
        sa.Column(
            "status",
            sqlmodel.sql.sqltypes.AutoString(length=30),
            nullable=False,
        ),
        sa.Column(
            "last_error_code",
            sqlmodel.sql.sqltypes.AutoString(length=80),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["owner_id"], ["user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("owner_id", "provider", name="uq_oauth_owner_provider"),
    )
    op.create_index(
        op.f("ix_oauthconnection_owner_id"), "oauthconnection", ["owner_id"]
    )

    op.create_table(
        "oauthattempt",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column(
            "state_hash",
            sqlmodel.sql.sqltypes.AutoString(length=64),
            nullable=False,
        ),
        sa.Column("encrypted_code_verifier", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["owner_id"], ["user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_oauthattempt_owner_id"), "oauthattempt", ["owner_id"])
    op.create_index(
        op.f("ix_oauthattempt_state_hash"),
        "oauthattempt",
        ["state_hash"],
        unique=True,
    )

    op.create_table(
        "youtubeeventreceipt",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("live_session_id", sa.Uuid(), nullable=False),
        sa.Column(
            "provider_message_id",
            sqlmodel.sql.sqltypes.AutoString(length=255),
            nullable=False,
        ),
        sa.Column(
            "event_type",
            sqlmodel.sql.sqltypes.AutoString(length=40),
            nullable=False,
        ),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_historical", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["live_session_id"], ["livesession.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "live_session_id",
            "provider_message_id",
            name="uq_youtube_receipt_provider",
        ),
    )
    op.create_index(
        op.f("ix_youtubeeventreceipt_live_session_id"),
        "youtubeeventreceipt",
        ["live_session_id"],
    )
    op.create_index(
        op.f("ix_youtubeeventreceipt_provider_message_id"),
        "youtubeeventreceipt",
        ["provider_message_id"],
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_youtubeeventreceipt_provider_message_id"),
        table_name="youtubeeventreceipt",
    )
    op.drop_index(
        op.f("ix_youtubeeventreceipt_live_session_id"),
        table_name="youtubeeventreceipt",
    )
    op.drop_table("youtubeeventreceipt")
    op.drop_index(op.f("ix_oauthattempt_state_hash"), table_name="oauthattempt")
    op.drop_index(op.f("ix_oauthattempt_owner_id"), table_name="oauthattempt")
    op.drop_table("oauthattempt")
    op.drop_index(op.f("ix_oauthconnection_owner_id"), table_name="oauthconnection")
    op.drop_table("oauthconnection")
    op.drop_index(
        op.f("ix_livesession_youtube_broadcast_id"), table_name="livesession"
    )
    op.drop_column("livesession", "youtube_connected_at")
    op.drop_column("livesession", "youtube_last_error")
    op.drop_column("livesession", "youtube_ingest_status")
    op.drop_column("livesession", "youtube_next_page_token")
    op.drop_column("livesession", "youtube_live_chat_id")
    op.drop_column("livesession", "youtube_broadcast_id")
