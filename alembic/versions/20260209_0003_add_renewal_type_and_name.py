"""add renewal type and renewal name

Revision ID: 20260209_0003
Revises: 20260203_0002
Create Date: 2026-02-09 00:03:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "20260209_0003"
down_revision = "20260203_0002"
branch_labels = None
depends_on = None


renewal_type_enum = sa.Enum(
    "Subscription",
    "Contract",
    "License",
    "Domain",
    "Certificate",
    "Other",
    name="renewal_type_enum",
)


def upgrade() -> None:
    bind = op.get_bind()
    renewal_type_enum.create(bind, checkfirst=True)

    op.add_column(
        "contracts",
        sa.Column("renewal_type", renewal_type_enum, nullable=False, server_default=sa.text("'Contract'")),
    )
    op.add_column("contracts", sa.Column("renewal_name", sa.String(length=255), nullable=True))

    op.execute(
        """
        UPDATE contracts
        SET
          renewal_type = (
            CASE
              WHEN contract_name ~ '^\\[[^\\]]+\\]' THEN
                CASE lower(regexp_replace(contract_name, '^\\[([^\\]]+)\\].*$', '\\1'))
                  WHEN 'subscription' THEN 'Subscription'
                  WHEN 'contract' THEN 'Contract'
                  WHEN 'license' THEN 'License'
                  WHEN 'domain' THEN 'Domain'
                  WHEN 'certificate' THEN 'Certificate'
                  WHEN 'other' THEN 'Other'
                  ELSE 'Other'
                END
              ELSE 'Contract'
            END
          )::renewal_type_enum,
          renewal_name = CASE
            WHEN contract_name ~ '^\\[[^\\]]+\\]\\s*'
              THEN NULLIF(regexp_replace(contract_name, '^\\[[^\\]]+\\]\\s*', ''), '')
            ELSE NULLIF(contract_name, '')
          END
        """
    )
    op.execute("UPDATE contracts SET renewal_name = vendor_name WHERE renewal_name IS NULL OR renewal_name = ''")

    op.alter_column("contracts", "renewal_name", nullable=False)
    op.alter_column("contracts", "renewal_type", server_default=None)


def downgrade() -> None:
    op.drop_column("contracts", "renewal_name")
    op.drop_column("contracts", "renewal_type")
    bind = op.get_bind()
    renewal_type_enum.drop(bind, checkfirst=True)
