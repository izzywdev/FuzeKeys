"""Executable coverage for durable SMS authorization schema migration."""

import importlib.util
from pathlib import Path

import sqlalchemy as sa

from alembic.migration import MigrationContext
from alembic.operations import Operations


def _load():
    path = (
        Path(__file__).parents[1]
        / "alembic/versions/d2026sms01_durable_sms_device_authorization.py"
    )
    spec = importlib.util.spec_from_file_location("sms_authz_migration", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_revision_chain_and_fresh_schema():
    migration = _load()
    assert migration.revision == "d2026sms01"
    assert migration.down_revision == "c2026conn01"

    engine = sa.create_engine("sqlite://")
    metadata = sa.MetaData()
    sa.Table("users", metadata, sa.Column("id", sa.Integer(), primary_key=True))
    metadata.create_all(engine)

    with engine.begin() as connection:
        migration.op = Operations(MigrationContext.configure(connection))
        migration.upgrade()
        inspector = sa.inspect(connection)
        assert {
            "sms_devices",
            "sms_otp_requests",
            "sms_otp_received",
            "sms_statistics",
        }.issubset(inspector.get_table_names())
        device_columns = {
            column["name"] for column in inspector.get_columns("sms_devices")
        }
        assert {"device_key_hash", "key_rotated_at"}.issubset(device_columns)
        request_columns = {
            column["name"] for column in inspector.get_columns("sms_otp_requests")
        }
        assert {"owner_user_id", "assigned_device_id"}.issubset(request_columns)


def test_downgrade_refuses_to_drop_live_authority_rows():
    migration = _load()
    engine = sa.create_engine("sqlite://")
    metadata = sa.MetaData()
    sa.Table("users", metadata, sa.Column("id", sa.Integer(), primary_key=True))
    metadata.create_all(engine)

    with engine.begin() as connection:
        migration.op = Operations(MigrationContext.configure(connection))
        migration.upgrade()
        connection.execute(
            sa.text(
                "INSERT INTO sms_devices "
                "(device_id, device_name, is_active, device_key_hash) "
                "VALUES ('device-a', 'device-a', 1, :digest)"
            ),
            {"digest": "a" * 64},
        )
        try:
            migration.downgrade()
        except RuntimeError as error:
            assert "cannot be removed" in str(error)
        else:
            raise AssertionError(
                "downgrade must refuse to delete live device authority"
            )


def test_upgrade_adds_authority_columns_to_legacy_sms_tables():
    migration = _load()
    engine = sa.create_engine("sqlite://")
    metadata = sa.MetaData()
    sa.Table("users", metadata, sa.Column("id", sa.Integer(), primary_key=True))
    sa.Table(
        "sms_devices",
        metadata,
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("device_id", sa.String(255), nullable=False, unique=True),
        sa.Column("device_name", sa.String(255), nullable=False),
    )
    sa.Table(
        "sms_otp_requests",
        metadata,
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("request_id", sa.String(255), nullable=False, unique=True),
        sa.Column("service", sa.String(255), nullable=False),
        sa.Column("timeout_at", sa.DateTime(), nullable=False),
    )
    metadata.create_all(engine)

    with engine.begin() as connection:
        migration.op = Operations(MigrationContext.configure(connection))
        migration.upgrade()
        inspector = sa.inspect(connection)
        assert {"device_key_hash", "key_rotated_at"}.issubset(
            {column["name"] for column in inspector.get_columns("sms_devices")}
        )
        assert {"owner_user_id", "assigned_device_id"}.issubset(
            {column["name"] for column in inspector.get_columns("sms_otp_requests")}
        )
