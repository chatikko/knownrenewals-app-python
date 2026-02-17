"""add slack integration tables and account timezone

Revision ID: 20260215_0006
Revises: 20260210_0005
Create Date: 2026-02-15 12:30:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "20260215_0006"
down_revision = "20260210_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "accounts",
        sa.Column("timezone", sa.String(length=64), nullable=False, server_default="UTC"),
    )
    op.alter_column("accounts", "timezone", server_default=None)

    op.create_table(
        "slack_integrations",
        sa.Column("account_id", sa.String(), nullable=False),
        sa.Column("workspace_id", sa.String(length=255), nullable=False),
        sa.Column("workspace_name", sa.String(length=255), nullable=False),
        sa.Column("bot_user_id", sa.String(length=255), nullable=True),
        sa.Column("bot_access_token_encrypted", sa.String(length=2048), nullable=True),
        sa.Column("bot_token_last4", sa.String(length=16), nullable=True),
        sa.Column("default_channel_id", sa.String(length=255), nullable=True),
        sa.Column("default_channel_name", sa.String(length=255), nullable=True),
        sa.Column("digest_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("instant_risk_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("instant_due_7d_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("digest_hour_local", sa.Integer(), nullable=False, server_default="9"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("is_degraded", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("last_error_code", sa.String(length=128), nullable=True),
        sa.Column("last_error_message", sa.String(length=1024), nullable=True),
        sa.Column("last_error_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("connected_by_user_id", sa.String(), nullable=True),
        sa.Column("connected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("disconnected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column("id", sa.String(), nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["connected_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("account_id", name="uq_slack_integrations_account"),
    )
    op.create_index("ix_slack_integrations_account_id", "slack_integrations", ["account_id"], unique=False)
    op.create_index("ix_slack_integrations_created_at", "slack_integrations", ["created_at"], unique=False)

    op.create_table(
        "slack_delivery_logs",
        sa.Column("account_id", sa.String(), nullable=False),
        sa.Column("contract_id", sa.String(), nullable=True),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("success", sa.Boolean(), nullable=False),
        sa.Column("http_status", sa.Integer(), nullable=True),
        sa.Column("error_code", sa.String(length=128), nullable=True),
        sa.Column("error_message", sa.String(length=1024), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column("id", sa.String(), nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["contract_id"], ["contracts.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_slack_delivery_logs_account_id", "slack_delivery_logs", ["account_id"], unique=False)
    op.create_index("ix_slack_delivery_logs_contract_id", "slack_delivery_logs", ["contract_id"], unique=False)
    op.create_index("ix_slack_delivery_logs_created_at", "slack_delivery_logs", ["created_at"], unique=False)

    op.create_table(
        "slack_alert_state",
        sa.Column("account_id", sa.String(), nullable=False),
        sa.Column("contract_id", sa.String(), nullable=True),
        sa.Column(
            "event_type",
            sa.Enum("risk", "due_7d", "daily_digest", name="slack_alert_event_type_enum"),
            nullable=False,
        ),
        sa.Column("event_date_key", sa.String(length=32), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("message_ts", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column("id", sa.String(), nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["contract_id"], ["contracts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("account_id", "contract_id", "event_type", "event_date_key", name="uq_slack_alert_state"),
    )
    op.create_index("ix_slack_alert_state_account_id", "slack_alert_state", ["account_id"], unique=False)
    op.create_index("ix_slack_alert_state_contract_id", "slack_alert_state", ["contract_id"], unique=False)
    op.create_index("ix_slack_alert_state_created_at", "slack_alert_state", ["created_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_slack_alert_state_created_at", table_name="slack_alert_state")
    op.drop_index("ix_slack_alert_state_contract_id", table_name="slack_alert_state")
    op.drop_index("ix_slack_alert_state_account_id", table_name="slack_alert_state")
    op.drop_table("slack_alert_state")

    op.drop_index("ix_slack_delivery_logs_created_at", table_name="slack_delivery_logs")
    op.drop_index("ix_slack_delivery_logs_contract_id", table_name="slack_delivery_logs")
    op.drop_index("ix_slack_delivery_logs_account_id", table_name="slack_delivery_logs")
    op.drop_table("slack_delivery_logs")

    op.drop_index("ix_slack_integrations_created_at", table_name="slack_integrations")
    op.drop_index("ix_slack_integrations_account_id", table_name="slack_integrations")
    op.drop_table("slack_integrations")

    op.drop_column("accounts", "timezone")
    op.execute("DROP TYPE IF EXISTS slack_alert_event_type_enum")
