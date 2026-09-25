"""connector credential metadata; secrets remain in OpenBao

Revision ID: a2026gmail01
Revises: f5b2c0d34e12
"""
from alembic import op
import sqlalchemy as sa

revision = "a2026gmail01"
down_revision = "f5b2c0d34e12"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "connector_credentials",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("owner_subject", sa.String(255), nullable=False),
        sa.Column("provider", sa.String(80), nullable=False),
        sa.Column("vault_ref", sa.String(500), nullable=False),
        sa.Column("identity_email", sa.String(320)),
        sa.Column("scopes", sa.JSON(), nullable=False),
        sa.Column("configuration", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("owner_subject", "provider", name="uq_connector_owner_provider"),
    )
    op.create_index("ix_connector_credentials_owner_subject", "connector_credentials", ["owner_subject"])


def downgrade():
    op.drop_index("ix_connector_credentials_owner_subject", table_name="connector_credentials")
    op.drop_table("connector_credentials")
