"""add lead magnet downloads table

Revision ID: 20260218_0007
Revises: 20260215_0006
Create Date: 2026-02-18 04:10:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "20260218_0007"
down_revision = "20260215_0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "lead_magnet_downloads",
        sa.Column("magnet_key", sa.String(length=64), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("normalized_email", sa.String(length=320), nullable=False),
        sa.Column(
            "status",
            sa.Enum("pending", "sent", "failed", "skipped", name="lead_magnet_status_enum"),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column("source_path", sa.String(length=512), nullable=True),
        sa.Column("utm_source", sa.String(length=255), nullable=True),
        sa.Column("utm_medium", sa.String(length=255), nullable=True),
        sa.Column("utm_campaign", sa.String(length=255), nullable=True),
        sa.Column("utm_term", sa.String(length=255), nullable=True),
        sa.Column("utm_content", sa.String(length=255), nullable=True),
        sa.Column("referrer", sa.String(length=1024), nullable=True),
        sa.Column("user_agent", sa.String(length=1024), nullable=True),
        sa.Column("ip_hash", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column("id", sa.String(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_lead_magnet_downloads_created_at",
        "lead_magnet_downloads",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        "ix_lead_magnet_downloads_normalized_email",
        "lead_magnet_downloads",
        ["normalized_email"],
        unique=False,
    )
    op.create_index(
        "ix_lead_magnet_downloads_status",
        "lead_magnet_downloads",
        ["status"],
        unique=False,
    )
    op.alter_column("lead_magnet_downloads", "status", server_default=None)


def downgrade() -> None:
    op.drop_index("ix_lead_magnet_downloads_status", table_name="lead_magnet_downloads")
    op.drop_index("ix_lead_magnet_downloads_normalized_email", table_name="lead_magnet_downloads")
    op.drop_index("ix_lead_magnet_downloads_created_at", table_name="lead_magnet_downloads")
    op.drop_table("lead_magnet_downloads")
    op.execute("DROP TYPE IF EXISTS lead_magnet_status_enum")
