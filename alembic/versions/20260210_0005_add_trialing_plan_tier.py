"""add trialing value to account plan tier enum

Revision ID: 20260210_0005
Revises: 20260210_0004
Create Date: 2026-02-10 10:40:00.000000
"""

from alembic import op


revision = "20260210_0005"
down_revision = "20260210_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TYPE plan_tier_enum ADD VALUE IF NOT EXISTS 'trialing'")


def downgrade() -> None:
    # PostgreSQL enum values are not safely removable in-place.
    pass
