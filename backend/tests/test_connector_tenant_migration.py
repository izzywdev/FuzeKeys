"""Additive migration leaves legacy custody quarantined; duplicate downgrade stops."""

import importlib.util
from pathlib import Path

import pytest
import sqlalchemy as sa

from alembic.migration import MigrationContext
from alembic.operations import Operations


def load_migration():
    path = (
        Path(__file__).parents[1] / "alembic/versions/c2026conn01_connector_tenant.py"
    )
    spec = importlib.util.spec_from_file_location("connector_tenant_migration", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_legacy_upgrade_is_not_a_tenant_backfill_and_duplicate_downgrade_refuses():
    engine = sa.create_engine("sqlite:///:memory:")
    metadata = sa.MetaData()
    table = sa.Table(
        "connector_credentials",
        metadata,
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("owner_subject", sa.String(255), nullable=False),
        sa.Column("provider", sa.String(80), nullable=False),
        sa.Column("vault_ref", sa.String(500), nullable=False),
        sa.UniqueConstraint(
            "owner_subject", "provider", name="uq_connector_owner_provider"
        ),
    )
    metadata.create_all(engine)
    module = load_migration()
    try:
        with engine.begin() as connection:
            connection.execute(
                table.insert().values(
                    owner_subject="owner",
                    provider="slack",
                    vault_ref="original-secret-path",
                )
            )
            module.op = Operations(MigrationContext.configure(connection))
            module.upgrade()
            old = connection.execute(
                sa.text("SELECT tenant_id, vault_ref FROM connector_credentials")
            ).one()
            assert old == (None, "original-secret-path")
            assert (
                connection.execute(
                    sa.text("SELECT count(*) FROM connector_grant_intents")
                ).scalar_one()
                == 0
            )
            connection.execute(
                sa.text(
                    "INSERT INTO connector_credentials (owner_subject, provider, vault_ref, tenant_id) VALUES ('owner', 'slack', 'tenant-a-ref', 'tenant-a'), ('owner','slack','tenant-b-ref','tenant-b')"
                )
            )
            with pytest.raises(RuntimeError):
                module.downgrade()
            assert "connector_grant_intents" in sa.inspect(connection).get_table_names()
    finally:
        engine.dispose()


def test_empty_upgrade_and_downgrade_round_trip():
    engine = sa.create_engine("sqlite:///:memory:")
    try:
        with engine.begin() as connection:
            connection.execute(
                sa.text(
                    "CREATE TABLE connector_credentials (id INTEGER PRIMARY KEY, owner_subject VARCHAR(255) NOT NULL, provider VARCHAR(80) NOT NULL, vault_ref VARCHAR(500) NOT NULL, CONSTRAINT uq_connector_owner_provider UNIQUE(owner_subject,provider))"
                )
            )
            module = load_migration()
            module.op = Operations(MigrationContext.configure(connection))
            module.upgrade()
            module.downgrade()
            assert "tenant_id" not in [
                column["name"]
                for column in sa.inspect(connection).get_columns(
                    "connector_credentials"
                )
            ]
            assert (
                "connector_grant_intents"
                not in sa.inspect(connection).get_table_names()
            )
    finally:
        engine.dispose()
