"""Migrate users off local password auth onto FuzeFront Security.

Revision ID: a6c3d1e45f23
Revises: f5b2c0d34e12
Create Date: 2026-08-02

FuzeKeys no longer authenticates anybody. Identity comes from the FuzeFront
Security API (`GET /v1/security/session`), so the `users` row becomes a local
PROJECTION of a FuzeFront subject rather than a credential store:

  + fuzefront_user_id  the stable FuzeFront subject id (`Identity.userId`),
                       nullable so existing rows can be adopted by email on
                       their owner's first FuzeFront-authenticated request
  - hashed_password    DROPPED. Storing user passwords is precisely the
                       coupling this migration removes; leaving the column
                       would leave the capability one commit away from
                       returning, and leave real password hashes at rest for a
                       login path that no longer exists.
  ~ master_key_hash    now nullable. It is FuzeKeys DOMAIN state (the vault
                       key verifier), not a login factor. It used to be
                       populated during local signup; a user provisioned from
                       a FuzeFront session has not set up their vault yet and
                       does so via POST /api/v1/auth/vault/setup.

Downgrade restores the columns structurally but CANNOT restore password
hashes — they are intentionally destroyed. Anyone downgrading must re-enrol
local passwords, which is the point.
"""

import sqlalchemy as sa
from alembic import op

revision = "a6c3d1e45f23"
down_revision = "f5b2c0d34e12"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.add_column(
            sa.Column("fuzefront_user_id", sa.String(length=255), nullable=True)
        )
        batch.alter_column(
            "master_key_hash",
            existing_type=sa.String(length=255),
            nullable=True,
        )
        batch.drop_column("hashed_password")

    op.create_index(
        "ix_users_fuzefront_user_id",
        "users",
        ["fuzefront_user_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_users_fuzefront_user_id", table_name="users")

    with op.batch_alter_table("users") as batch:
        # Re-added as nullable: the original hashes are gone for good, and a
        # NOT NULL column with no value to put in it cannot be created.
        batch.add_column(
            sa.Column("hashed_password", sa.String(length=255), nullable=True)
        )
        batch.drop_column("fuzefront_user_id")
        # master_key_hash is deliberately left nullable: rows provisioned after
        # the upgrade may legitimately have no vault yet, so tightening it back
        # to NOT NULL would fail.
