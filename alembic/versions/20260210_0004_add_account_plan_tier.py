"""add account plan tier for seat limits

Revision ID: 20260210_0004
Revises: 20260209_0003
Create Date: 2026-02-10 08:15:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "20260210_0004"
down_revision = "20260209_0003"
branch_labels = None
depends_on = None


plan_tier_enum = sa.Enum("founders", "pro", "team", name="plan_tier_enum")


def upgrade() -> None:
    bind = op.get_bind()
    plan_tier_enum.create(bind, checkfirst=True)
    op.add_column(
        "accounts",
        sa.Column("plan_tier", plan_tier_enum, nullable=False, server_default=sa.text("'pro'")),
    )
    op.alter_column("accounts", "plan_tier", server_default=None)


def downgrade() -> None:
    op.drop_column("accounts", "plan_tier")
    bind = op.get_bind()
    plan_tier_enum.drop(bind, checkfirst=True)
