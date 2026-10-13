"""Local reference index of FuzeFront users / orgs / org members (FKY-10).

Revision ID: e2026evt02
Revises: e2026evt01

Purely additive: three new tables, no existing table is touched, so downgrade is
a plain drop. Ids are bare FuzeFront spine ids; no PII and no cross-service or
cross-aggregate foreign keys (see app/models/fuzefront_refs.py).
"""

import sqlalchemy as sa

from alembic import op

revision = "e2026evt02"
down_revision = "e2026evt01"
branch_labels = None
depends_on = None


def _now():
    return sa.func.now()


def _ts(name):
    return sa.Column(
        name, sa.DateTime(timezone=True), server_default=_now(), nullable=False
    )


def upgrade():
    op.create_table(
        "ref_users",
        sa.Column("user_id", sa.String(64), primary_key=True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("deletion_mode", sa.String(8), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source_version", sa.Integer(), nullable=False),
        _ts("created_at"),
        _ts("updated_at"),
    )
    op.create_table(
        "ref_orgs",
        sa.Column("org_id", sa.String(64), primary_key=True),
        sa.Column("owner_user_id", sa.String(64), nullable=True),
        sa.Column("source_version", sa.Integer(), nullable=False),
        _ts("created_at"),
        _ts("updated_at"),
    )
    op.create_table(
        "ref_org_members",
        sa.Column("org_id", sa.String(64), nullable=False),
        sa.Column("user_id", sa.String(64), nullable=False),
        sa.Column("role", sa.String(64), nullable=False),
        sa.Column("source_version", sa.Integer(), nullable=False),
        _ts("created_at"),
        _ts("updated_at"),
        sa.PrimaryKeyConstraint("org_id", "user_id"),
    )
    op.create_index("ix_ref_org_members_user_id", "ref_org_members", ["user_id"])


def downgrade():
    op.drop_index("ix_ref_org_members_user_id", table_name="ref_org_members")
    op.drop_table("ref_org_members")
    op.drop_table("ref_orgs")
    op.drop_table("ref_users")
