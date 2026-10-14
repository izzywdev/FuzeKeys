"""Event consumer runtime: inbox, aggregate version guard, dead letters, outbox.

Revision ID: e2026evt01
Revises: d2026sms01

FKY-9 scaffolding for FuzeFront user/org events. Purely additive: new tables
only, no existing table is touched, so downgrade is a plain drop. No payload
bodies or PII are stored (see app/models/event_runtime.py).
"""

import sqlalchemy as sa

from alembic import op

revision = "e2026evt01"
down_revision = "d2026sms01"
branch_labels = None
depends_on = None


def _now():
    return sa.func.now()


def upgrade():
    op.create_table(
        "event_inbox",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("event_id", sa.String(64), nullable=False),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("aggregate_type", sa.String(32), nullable=False),
        sa.Column("aggregate_id", sa.String(64), nullable=False),
        sa.Column("aggregate_version", sa.Integer(), nullable=False),
        sa.Column("outcome", sa.String(16), nullable=False),
        sa.Column(
            "received_at",
            sa.DateTime(timezone=True),
            server_default=_now(),
            nullable=False,
        ),
        sa.UniqueConstraint("event_id", name="uq_event_inbox_event_id"),
    )
    op.create_table(
        "event_aggregate_versions",
        sa.Column("aggregate_type", sa.String(32), nullable=False),
        sa.Column("aggregate_id", sa.String(64), nullable=False),
        sa.Column("last_version", sa.Integer(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=_now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("aggregate_type", "aggregate_id"),
    )
    op.create_table(
        "event_dead_letters",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("event_id", sa.String(64), nullable=True),
        sa.Column("event_type", sa.String(64), nullable=True),
        sa.Column("reason_code", sa.String(32), nullable=False),
        sa.Column("error_summary", sa.Text(), nullable=False),
        sa.Column("payload_sha256", sa.String(64), nullable=False),
        sa.Column(
            "received_at",
            sa.DateTime(timezone=True),
            server_default=_now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_event_dead_letters_event_id", "event_dead_letters", ["event_id"]
    )
    op.create_table(
        "event_outbox",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("event_id", sa.String(64), nullable=False),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("aggregate_type", sa.String(32), nullable=False),
        sa.Column("aggregate_id", sa.String(64), nullable=False),
        sa.Column("aggregate_version", sa.Integer(), nullable=False),
        sa.Column("payload", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=_now(),
            nullable=False,
        ),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("event_id", name="uq_event_outbox_event_id"),
    )
    op.create_index(
        "ix_event_outbox_unpublished", "event_outbox", ["published_at", "id"]
    )


def downgrade():
    op.drop_index("ix_event_outbox_unpublished", table_name="event_outbox")
    op.drop_table("event_outbox")
    op.drop_index("ix_event_dead_letters_event_id", table_name="event_dead_letters")
    op.drop_table("event_dead_letters")
    op.drop_table("event_aggregate_versions")
    op.drop_table("event_inbox")
