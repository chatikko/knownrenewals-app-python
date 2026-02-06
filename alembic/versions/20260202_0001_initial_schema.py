"""initial schema

Revision ID: 20260202_0001
Revises:
Create Date: 2026-02-02 00:01:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "20260202_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "accounts",
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("owner_email", sa.String(length=255), nullable=False),
        sa.Column("stripe_customer_id", sa.String(length=255), nullable=True),
        sa.Column("stripe_subscription_id", sa.String(length=255), nullable=True),
        sa.Column("plan", sa.Enum("monthly", "yearly", name="plan_enum"), nullable=True),
        sa.Column(
            "status",
            sa.Enum("inactive", "trialing", "active", "past_due", "canceled", name="account_status_enum"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column("id", sa.String(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("stripe_customer_id"),
        sa.UniqueConstraint("stripe_subscription_id"),
    )
    op.create_index("ix_accounts_created_at", "accounts", ["created_at"], unique=False)
    op.create_index("ix_accounts_owner_email", "accounts", ["owner_email"], unique=False)

    op.create_table(
        "users",
        sa.Column("account_id", sa.String(), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=True),
        sa.Column("is_email_verified", sa.Boolean(), nullable=True),
        sa.Column("is_admin", sa.Boolean(), nullable=True),
        sa.Column("email_verification_hash", sa.String(length=64), nullable=True),
        sa.Column("email_verification_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column("id", sa.String(), nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
    )
    op.create_index("ix_users_account_id", "users", ["account_id"], unique=False)
    op.create_index("ix_users_created_at", "users", ["created_at"], unique=False)

    op.create_table(
        "contracts",
        sa.Column("account_id", sa.String(), nullable=False),
        sa.Column("vendor_name", sa.String(length=255), nullable=False),
        sa.Column("contract_name", sa.String(length=255), nullable=True),
        sa.Column("renewal_date", sa.Date(), nullable=False),
        sa.Column("notice_period_days", sa.Integer(), nullable=False),
        sa.Column("notice_deadline", sa.Date(), nullable=False),
        sa.Column("owner_email", sa.String(length=255), nullable=False),
        sa.Column("status", sa.Enum("safe", "soon", "risk", name="contract_status_enum"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column("id", sa.String(), nullable=False),
        sa.CheckConstraint("notice_period_days >= 0", name="notice_period_non_negative"),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_contracts_account_id", "contracts", ["account_id"], unique=False)
    op.create_index("ix_contracts_created_at", "contracts", ["created_at"], unique=False)
    op.create_index("ix_contracts_notice_deadline", "contracts", ["notice_deadline"], unique=False)
    op.create_index("ix_contracts_owner_email", "contracts", ["owner_email"], unique=False)

    op.create_table(
        "billing_events",
        sa.Column("account_id", sa.String(), nullable=True),
        sa.Column("stripe_event_id", sa.String(length=255), nullable=False),
        sa.Column("event_type", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column("id", sa.String(), nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("stripe_event_id"),
    )
    op.create_index("ix_billing_events_created_at", "billing_events", ["created_at"], unique=False)

    op.create_table(
        "refresh_tokens",
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("replaced_by", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column("id", sa.String(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index("ix_refresh_tokens_expires_at", "refresh_tokens", ["expires_at"], unique=False)
    op.create_index("ix_refresh_tokens_user_id", "refresh_tokens", ["user_id"], unique=False)

    op.create_table(
        "auth_events",
        sa.Column("user_id", sa.String(), nullable=True),
        sa.Column("event_type", sa.String(length=50), nullable=False),
        sa.Column("ip_address", sa.String(length=64), nullable=True),
        sa.Column("user_agent", sa.String(length=255), nullable=True),
        sa.Column("success", sa.Boolean(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column("id", sa.String(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_auth_events_created_at", "auth_events", ["created_at"], unique=False)
    op.create_index("ix_auth_events_user_id", "auth_events", ["user_id"], unique=False)

    op.create_table(
        "contract_reminder_logs",
        sa.Column("contract_id", sa.String(), nullable=False),
        sa.Column("reminder_date", sa.Date(), nullable=False),
        sa.Column("days_before", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column("id", sa.String(), nullable=False),
        sa.CheckConstraint("days_before >= 0", name="days_before_positive"),
        sa.ForeignKeyConstraint(["contract_id"], ["contracts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("contract_id", "reminder_date", "days_before", name="uq_contract_reminder"),
    )
    op.create_index(
        "ix_contract_reminders_created_at", "contract_reminder_logs", ["created_at"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_contract_reminders_created_at", table_name="contract_reminder_logs")
    op.drop_table("contract_reminder_logs")
    op.drop_index("ix_auth_events_user_id", table_name="auth_events")
    op.drop_index("ix_auth_events_created_at", table_name="auth_events")
    op.drop_table("auth_events")
    op.drop_index("ix_refresh_tokens_user_id", table_name="refresh_tokens")
    op.drop_index("ix_refresh_tokens_expires_at", table_name="refresh_tokens")
    op.drop_table("refresh_tokens")
    op.drop_index("ix_billing_events_created_at", table_name="billing_events")
    op.drop_table("billing_events")
    op.drop_index("ix_contracts_owner_email", table_name="contracts")
    op.drop_index("ix_contracts_notice_deadline", table_name="contracts")
    op.drop_index("ix_contracts_created_at", table_name="contracts")
    op.drop_index("ix_contracts_account_id", table_name="contracts")
    op.drop_table("contracts")
    op.drop_index("ix_users_created_at", table_name="users")
    op.drop_index("ix_users_account_id", table_name="users")
    op.drop_table("users")
    op.drop_index("ix_accounts_owner_email", table_name="accounts")
    op.drop_index("ix_accounts_created_at", table_name="accounts")
    op.drop_table("accounts")
