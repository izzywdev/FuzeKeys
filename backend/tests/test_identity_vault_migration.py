"""
Structural test for the Phase 1 Alembic migration.

Loads the migration file by path (importing `alembic.versions.<x>` would collide
with the installed `alembic` package), then asserts the revision chain and that
every Phase 1 table/column op is present.
"""
import importlib.util
import os

MIG_PATH = os.path.abspath(os.path.join(
    os.path.dirname(__file__), "..", "alembic", "versions",
    "e4a1f0b21c01_identity_vault_phase1.py"))


def _load():
    spec = importlib.util.spec_from_file_location("phase1_mig", MIG_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_revision_chain():
    m = _load()
    assert m.revision == "e4a1f0b21c01"
    assert m.down_revision == "c2019ga02d9g"
    assert callable(m.upgrade) and callable(m.downgrade)


def test_all_phase1_tables_and_columns_present():
    src = open(MIG_PATH).read()
    for table in ["organizations", "organization_members", "identity_cards",
                  "api_credentials", "agents", "agent_scopes",
                  "approval_requests", "audit_log"]:
        assert f'"{table}"' in src, f"missing create_table for {table}"
    assert 'add_column("identities"' in src
    assert 'add_column("accounts"' in src
    # No secret-bearing columns introduced by the migration.
    for forbidden in ["password", "secret", "token_value", "card_number", "cvv"]:
        assert forbidden not in src.lower()
