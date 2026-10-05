"""Persist verified, unique platform identity bindings.

Revision ID: b2026link01
Revises: a2026gmail01
"""

import sqlalchemy as sa

from alembic import op

revision = "b2026link01"
down_revision = "a2026gmail01"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "platform_identities",
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), primary_key=True),
        sa.Column("subject", sa.String(255), nullable=False),
        sa.Column("tenant", sa.String(255), nullable=False),
        sa.Column(
            "verified_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("subject", "tenant", name="uq_platform_subject_tenant"),
    )


def downgrade():
    # No existing users or credential records are changed by this migration.
    # Downgrade discards bindings: users must explicitly re-link after upgrade.
    op.drop_table("platform_identities")
