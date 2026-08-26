"""secret-broker: broker_grants table

Backs the secretless agent-to-agent handoff. Stores NO secret material — only the
opaque grant id, handle fingerprint, bound redeemer transport identity, a
reference to the vault secret (or a capability operation), lifecycle, and the
macaroon root verification key (a server-side signing key, never the user's
secret).
"""
import sqlalchemy as sa

from alembic import op

revision = "f5b2c0d34e12"
down_revision = "e4a1f0b21c01"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "broker_grants",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("grant_id", sa.String(length=64), nullable=False, unique=True),
        sa.Column("handle_fingerprint", sa.String(length=128), nullable=False),
        sa.Column("grantor_identity", sa.String(length=255), nullable=False),
        sa.Column("redeemer_identity", sa.String(length=255), nullable=False),
        sa.Column("secret_ref", sa.String(length=300), nullable=True),
        sa.Column("operation", sa.String(length=120), nullable=True),
        sa.Column("scope", sa.Text(), nullable=False, server_default="{}"),
        sa.Column(
            "sensitivity", sa.String(length=20), nullable=False, server_default="medium"
        ),
        sa.Column("ttl_seconds", sa.Integer(), nullable=False),
        sa.Column("single_use", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("root_key", sa.LargeBinary(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("redemption_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("redeemed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("redeemed_by", sa.String(length=255), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_reason", sa.String(length=255), nullable=True),
        sa.Column(
            "approval_request_id",
            sa.Integer(),
            sa.ForeignKey("approval_requests.id"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_broker_grants_grant_id", "broker_grants", ["grant_id"], unique=True
    )
    op.create_index(
        "ix_broker_grants_handle_fingerprint", "broker_grants", ["handle_fingerprint"]
    )
    op.create_index(
        "ix_broker_grants_redeemer_identity", "broker_grants", ["redeemer_identity"]
    )
    op.create_index(
        "ix_broker_grants_grantor_identity", "broker_grants", ["grantor_identity"]
    )
    op.create_index("ix_broker_grants_expires_at", "broker_grants", ["expires_at"])


def downgrade():
    for idx in [
        "ix_broker_grants_expires_at",
        "ix_broker_grants_grantor_identity",
        "ix_broker_grants_redeemer_identity",
        "ix_broker_grants_handle_fingerprint",
        "ix_broker_grants_grant_id",
    ]:
        op.drop_index(idx, table_name="broker_grants")
    op.drop_table("broker_grants")
