"""add extended contract metadata fields

Revision ID: 20260218_0008
Revises: 20260218_0007
Create Date: 2026-02-18 11:35:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "20260218_0008"
down_revision = "20260218_0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("contracts", sa.Column("external_contract_id", sa.String(length=64), nullable=True))
    op.add_column("contracts", sa.Column("category", sa.String(length=100), nullable=True))
    op.add_column("contracts", sa.Column("start_date", sa.Date(), nullable=True))
    op.add_column("contracts", sa.Column("billing_frequency", sa.String(length=50), nullable=True))
    op.add_column("contracts", sa.Column("contract_value", sa.Numeric(precision=12, scale=2), nullable=True))
    op.add_column("contracts", sa.Column("annualized_value", sa.Numeric(precision=12, scale=2), nullable=True))
    op.add_column("contracts", sa.Column("auto_renew", sa.Boolean(), nullable=True))
    op.add_column("contracts", sa.Column("notes", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("contracts", "notes")
    op.drop_column("contracts", "auto_renew")
    op.drop_column("contracts", "annualized_value")
    op.drop_column("contracts", "contract_value")
    op.drop_column("contracts", "billing_frequency")
    op.drop_column("contracts", "start_date")
    op.drop_column("contracts", "category")
    op.drop_column("contracts", "external_contract_id")
