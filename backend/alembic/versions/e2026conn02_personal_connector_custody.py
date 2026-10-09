"""Enforce one personal connector credential per user and provider.

Revision ID: e2026conn02
Revises: d2026sms01
"""

import sqlalchemy as sa

from alembic import op

revision = "e2026conn02"
down_revision = "d2026sms01"
branch_labels = None
depends_on = None


def upgrade():
    op.create_index(
        "uq_connector_personal_owner_provider",
        "connector_credentials",
        ["owner_subject", "provider"],
        unique=True,
        postgresql_where=sa.text("tenant_id IS NULL"),
        sqlite_where=sa.text("tenant_id IS NULL"),
    )


def downgrade():
    op.drop_index(
        "uq_connector_personal_owner_provider", table_name="connector_credentials"
    )
