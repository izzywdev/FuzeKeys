"""identity vault phase 1: tenancy, agents, approvals, audit, vault handles"""
from alembic import op
import sqlalchemy as sa

revision = "e4a1f0b21c01"
down_revision = "c2019ga02d9g"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "organizations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("slug", sa.String(length=100), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "organization_members",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False, server_default="member"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("organization_id", "user_id", name="uq_org_member"),
    )
    op.create_table(
        "identity_cards",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("identity_id", sa.Integer(), sa.ForeignKey("identities.id"), nullable=False),
        sa.Column("brand", sa.String(length=40)),
        sa.Column("last4", sa.String(length=4)),
        sa.Column("exp_month", sa.Integer()),
        sa.Column("exp_year", sa.Integer()),
        sa.Column("vault_item_ref", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "api_credentials",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("identity_id", sa.Integer(), sa.ForeignKey("identities.id"), nullable=False),
        sa.Column("service", sa.String(length=120), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("openbao_path", sa.String(length=300), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "agents",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("token_hash", sa.String(length=255), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "agent_scopes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("agent_id", sa.Integer(), sa.ForeignKey("agents.id"), nullable=False),
        sa.Column("scope_type", sa.String(length=20), nullable=False),
        sa.Column("scope_ref", sa.String(length=120), nullable=False),
    )
    op.create_table(
        "approval_requests",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("agent_id", sa.Integer(), sa.ForeignKey("agents.id"), nullable=False),
        sa.Column("resource_ref", sa.String(length=300), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("requested_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("decided_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "audit_log",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("agent_id", sa.Integer(), nullable=True),
        sa.Column("on_behalf_user_id", sa.Integer(), nullable=True),
        sa.Column("identity_id", sa.Integer(), nullable=True),
        sa.Column("resource_ref", sa.String(length=300), nullable=False),
        sa.Column("decision", sa.String(length=40), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.add_column("identities", sa.Column("org_id", sa.Integer(), sa.ForeignKey("organizations.id"), nullable=True))
    op.add_column("identities", sa.Column("vault_collection_ref", sa.String(length=255), nullable=True))
    op.add_column("accounts", sa.Column("vault_item_ref", sa.String(length=255), nullable=True))


def downgrade():
    op.drop_column("accounts", "vault_item_ref")
    op.drop_column("identities", "vault_collection_ref")
    op.drop_column("identities", "org_id")
    for table in ["audit_log", "approval_requests", "agent_scopes", "agents",
                  "api_credentials", "identity_cards", "organization_members", "organizations"]:
        op.drop_table(table)
