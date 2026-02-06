"""fix timezone-aware datetime columns

Revision ID: 20260203_0002
Revises: 20260202_0001
Create Date: 2026-02-03 17:30:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "20260203_0002"
down_revision = "20260202_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "users",
        "email_verification_expires_at",
        existing_type=sa.DateTime(),
        type_=sa.DateTime(timezone=True),
        existing_nullable=True,
        postgresql_using="email_verification_expires_at AT TIME ZONE 'UTC'",
    )
    op.alter_column(
        "refresh_tokens",
        "expires_at",
        existing_type=sa.DateTime(),
        type_=sa.DateTime(timezone=True),
        existing_nullable=False,
        postgresql_using="expires_at AT TIME ZONE 'UTC'",
    )
    op.alter_column(
        "refresh_tokens",
        "revoked_at",
        existing_type=sa.DateTime(),
        type_=sa.DateTime(timezone=True),
        existing_nullable=True,
        postgresql_using="revoked_at AT TIME ZONE 'UTC'",
    )


def downgrade() -> None:
    op.alter_column(
        "refresh_tokens",
        "revoked_at",
        existing_type=sa.DateTime(timezone=True),
        type_=sa.DateTime(),
        existing_nullable=True,
    )
    op.alter_column(
        "refresh_tokens",
        "expires_at",
        existing_type=sa.DateTime(timezone=True),
        type_=sa.DateTime(),
        existing_nullable=False,
    )
    op.alter_column(
        "users",
        "email_verification_expires_at",
        existing_type=sa.DateTime(timezone=True),
        type_=sa.DateTime(),
        existing_nullable=True,
    )
