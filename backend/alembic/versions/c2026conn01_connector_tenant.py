"""Quarantine unbound connectors and persist scoped owner grant intentions.

Revision ID: c2026conn01
Revises: b2026link01
"""

import sqlalchemy as sa

from alembic import op

revision = "c2026conn01"
down_revision = "b2026link01"
branch_labels = None
depends_on = None


def upgrade():
    # No data update: old records cannot acquire authority from guessed tenants.
    with op.batch_alter_table("connector_credentials") as batch:
        batch.add_column(sa.Column("tenant_id", sa.String(255), nullable=True))
        batch.drop_constraint("uq_connector_owner_provider", type_="unique")
        batch.create_unique_constraint(
            "uq_connector_tenant_owner_provider",
            ["tenant_id", "owner_subject", "provider"],
        )
        batch.create_index("ix_connector_credentials_tenant_id", ["tenant_id"])
    op.create_table(
        "connector_grant_intents",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.String(255), nullable=False),
        sa.Column("owner_subject", sa.String(255), nullable=False),
        sa.Column("provider", sa.String(80), nullable=False),
        sa.Column("resource_key", sa.String(80), nullable=False),
        sa.Column("desired_state", sa.String(16), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "tenant_id", "resource_key", name="uq_connector_grant_intent"
        ),
    )


def downgrade():
    bound = (
        op.get_bind()
        .execute(
            sa.text(
                "SELECT id FROM connector_credentials WHERE tenant_id IS NOT NULL LIMIT 1"
            )
        )
        .first()
    )
    if bound:
        raise RuntimeError(
            "Tenant-bound connector rows require reviewed custody retirement before downgrade"
        )
    # Refuse destructive collapse when one subject/provider exists in two tenants.
    duplicates = (
        op.get_bind()
        .execute(
            sa.text(
                "SELECT owner_subject, provider FROM connector_credentials GROUP BY owner_subject, provider HAVING COUNT(*) > 1 LIMIT 1"
            )
        )
        .first()
    )
    if duplicates:
        raise RuntimeError(
            "Connector tenant isolation cannot be collapsed while duplicate owner/provider rows exist"
        )
    op.drop_table("connector_grant_intents")
    with op.batch_alter_table("connector_credentials") as batch:
        batch.drop_index("ix_connector_credentials_tenant_id")
        batch.drop_constraint("uq_connector_tenant_owner_provider", type_="unique")
        batch.create_unique_constraint(
            "uq_connector_owner_provider", ["owner_subject", "provider"]
        )
        batch.drop_column("tenant_id")
