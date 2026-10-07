"""Persist SMS device principals and creator-scoped OTP assignments.

Revision ID: d2026sms01
Revises: c2026conn01
"""

import sqlalchemy as sa

from alembic import op

revision = "d2026sms01"
down_revision = "c2026conn01"
branch_labels = None
depends_on = None


def _columns(inspector, table):
    return {column["name"] for column in inspector.get_columns(table)}


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "sms_devices" not in tables:
        op.create_table(
            "sms_devices",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("device_id", sa.String(255), nullable=False),
            sa.Column("device_name", sa.String(255), nullable=False),
            sa.Column("os_version", sa.String(100), nullable=True),
            sa.Column("app_version", sa.String(50), nullable=True),
            sa.Column(
                "is_active", sa.Boolean(), nullable=False, server_default=sa.true()
            ),
            sa.Column("device_key_hash", sa.String(64), nullable=True),
            sa.Column("key_rotated_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_seen", sa.DateTime(timezone=True), nullable=True),
            sa.UniqueConstraint("device_id", name="uq_sms_devices_device_id"),
        )
        op.create_index("ix_sms_devices_device_id", "sms_devices", ["device_id"])
    else:
        columns = _columns(inspector, "sms_devices")
        with op.batch_alter_table("sms_devices") as batch:
            if "device_key_hash" not in columns:
                batch.add_column(
                    sa.Column("device_key_hash", sa.String(64), nullable=True)
                )
            if "key_rotated_at" not in columns:
                batch.add_column(
                    sa.Column(
                        "key_rotated_at", sa.DateTime(timezone=True), nullable=True
                    )
                )

    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    if "sms_otp_requests" not in tables:
        op.create_table(
            "sms_otp_requests",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("request_id", sa.String(255), nullable=False),
            sa.Column("service", sa.String(255), nullable=False),
            sa.Column("status", sa.String(50), nullable=True),
            sa.Column("otp_code", sa.String(20), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("timeout_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("device_id", sa.String(255), nullable=True),
            sa.Column(
                "owner_user_id",
                sa.Integer(),
                sa.ForeignKey("users.id"),
                nullable=True,
            ),
            sa.Column(
                "assigned_device_id",
                sa.String(255),
                sa.ForeignKey("sms_devices.device_id"),
                nullable=True,
            ),
            sa.UniqueConstraint("request_id", name="uq_sms_otp_requests_request_id"),
        )
        op.create_index(
            "ix_sms_otp_requests_request_id", "sms_otp_requests", ["request_id"]
        )
        op.create_index(
            "ix_sms_otp_requests_owner_user_id",
            "sms_otp_requests",
            ["owner_user_id"],
        )
        op.create_index(
            "ix_sms_otp_requests_assigned_device_id",
            "sms_otp_requests",
            ["assigned_device_id"],
        )
    else:
        columns = _columns(inspector, "sms_otp_requests")
        with op.batch_alter_table("sms_otp_requests") as batch:
            if "owner_user_id" not in columns:
                batch.add_column(
                    sa.Column("owner_user_id", sa.Integer(), nullable=True)
                )
                batch.create_foreign_key(
                    "fk_sms_otp_requests_owner_user_id",
                    "users",
                    ["owner_user_id"],
                    ["id"],
                )
                batch.create_index(
                    "ix_sms_otp_requests_owner_user_id", ["owner_user_id"]
                )
            if "assigned_device_id" not in columns:
                batch.add_column(
                    sa.Column("assigned_device_id", sa.String(255), nullable=True)
                )
                batch.create_foreign_key(
                    "fk_sms_otp_requests_assigned_device_id",
                    "sms_devices",
                    ["assigned_device_id"],
                    ["device_id"],
                )
                batch.create_index(
                    "ix_sms_otp_requests_assigned_device_id", ["assigned_device_id"]
                )

    tables = set(sa.inspect(bind).get_table_names())
    if "sms_otp_received" not in tables:
        op.create_table(
            "sms_otp_received",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("device_id", sa.String(255), nullable=False),
            sa.Column("otp_code", sa.String(20), nullable=False),
            sa.Column("sender", sa.String(255), nullable=True),
            sa.Column("message_body", sa.Text(), nullable=True),
            sa.Column("confidence", sa.Float(), nullable=True),
            sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("matched_request_id", sa.String(255), nullable=True),
        )
        op.create_index(
            "ix_sms_otp_received_device_id", "sms_otp_received", ["device_id"]
        )

    tables = set(sa.inspect(bind).get_table_names())
    if "sms_statistics" not in tables:
        op.create_table(
            "sms_statistics",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("device_id", sa.String(255), nullable=False),
            sa.Column("date", sa.DateTime(timezone=True), nullable=True),
            sa.Column("total_sms_processed", sa.Integer(), nullable=True),
            sa.Column("otps_detected", sa.Integer(), nullable=True),
            sa.Column("otps_matched", sa.Integer(), nullable=True),
            sa.Column("average_confidence", sa.Float(), nullable=True),
        )
        op.create_index("ix_sms_statistics_device_id", "sms_statistics", ["device_id"])


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    for table in (
        "sms_otp_received",
        "sms_otp_requests",
        "sms_statistics",
        "sms_devices",
    ):
        if table in tables:
            row = bind.execute(sa.text(f"SELECT 1 FROM {table} LIMIT 1")).first()
            if row:
                raise RuntimeError(
                    "SMS authorization custody cannot be removed while SMS rows exist"
                )

    for table in (
        "sms_otp_received",
        "sms_otp_requests",
        "sms_statistics",
        "sms_devices",
    ):
        if table in tables:
            op.drop_table(table)
