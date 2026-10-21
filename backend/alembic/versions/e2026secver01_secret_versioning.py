"""Secret versioning and environment-grouped rollback.

Adds immutable per-secret version history and environment (secret-list)
snapshots so an individual secret or a whole environment can be rolled back to
prior values. All value storage is ciphertext; these tables never hold
plaintext.

Revision ID: e2026secver01
Revises: d2026sms01
"""

import sqlalchemy as sa

from alembic import op

revision = "e2026secver01"
down_revision = "d2026sms01"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "secret_environments" not in tables:
        op.create_table(
            "secret_environments",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column(
                "user_id",
                sa.Integer(),
                sa.ForeignKey("users.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "org_id",
                sa.Integer(),
                sa.ForeignKey("organizations.id"),
                nullable=True,
            ),
            sa.Column("name", sa.String(100), nullable=False),
            sa.Column("description", sa.String(500), nullable=True),
            sa.Column(
                "current_snapshot_version",
                sa.Integer(),
                nullable=False,
                server_default="0",
            ),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
            sa.UniqueConstraint("user_id", "name", name="uq_secret_env_user_name"),
        )
        op.create_index(
            "ix_secret_environments_user_id", "secret_environments", ["user_id"]
        )

    if "secrets" not in tables:
        op.create_table(
            "secrets",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column(
                "environment_id",
                sa.Integer(),
                sa.ForeignKey("secret_environments.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("key", sa.String(255), nullable=False),
            sa.Column("description", sa.String(500), nullable=True),
            sa.Column(
                "current_version", sa.Integer(), nullable=False, server_default="0"
            ),
            sa.Column(
                "is_deleted",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            ),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
            sa.UniqueConstraint("environment_id", "key", name="uq_secret_env_key"),
        )
        op.create_index("ix_secrets_environment_id", "secrets", ["environment_id"])

    if "secret_versions" not in tables:
        op.create_table(
            "secret_versions",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column(
                "secret_id",
                sa.Integer(),
                sa.ForeignKey("secrets.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("version", sa.Integer(), nullable=False),
            sa.Column("encrypted_value", sa.Text(), nullable=False),
            sa.Column("value_hmac", sa.String(64), nullable=True),
            sa.Column("change_comment", sa.String(500), nullable=True),
            sa.Column(
                "is_rollback", sa.Boolean(), nullable=False, server_default=sa.false()
            ),
            sa.Column("rolled_back_from_version", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_by_user_id", sa.Integer(), nullable=True),
            sa.UniqueConstraint("secret_id", "version", name="uq_secret_version"),
        )
        op.create_index(
            "ix_secret_versions_secret_id", "secret_versions", ["secret_id"]
        )

    if "environment_snapshots" not in tables:
        op.create_table(
            "environment_snapshots",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column(
                "environment_id",
                sa.Integer(),
                sa.ForeignKey("secret_environments.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("snapshot_version", sa.Integer(), nullable=False),
            sa.Column("label", sa.String(200), nullable=True),
            sa.Column(
                "is_rollback", sa.Boolean(), nullable=False, server_default=sa.false()
            ),
            sa.Column("rolled_back_from_snapshot", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_by_user_id", sa.Integer(), nullable=True),
            sa.UniqueConstraint(
                "environment_id",
                "snapshot_version",
                name="uq_env_snapshot_version",
            ),
        )
        op.create_index(
            "ix_environment_snapshots_environment_id",
            "environment_snapshots",
            ["environment_id"],
        )

    if "secret_snapshot_entries" not in tables:
        op.create_table(
            "secret_snapshot_entries",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column(
                "snapshot_id",
                sa.Integer(),
                sa.ForeignKey("environment_snapshots.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "secret_id",
                sa.Integer(),
                sa.ForeignKey("secrets.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "secret_version_id",
                sa.Integer(),
                sa.ForeignKey("secret_versions.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("secret_key", sa.String(255), nullable=False),
            sa.Column("version", sa.Integer(), nullable=False),
        )
        op.create_index(
            "ix_secret_snapshot_entries_snapshot_id",
            "secret_snapshot_entries",
            ["snapshot_id"],
        )


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    for table in (
        "secret_snapshot_entries",
        "environment_snapshots",
        "secret_versions",
        "secrets",
        "secret_environments",
    ):
        if table in tables:
            op.drop_table(table)
