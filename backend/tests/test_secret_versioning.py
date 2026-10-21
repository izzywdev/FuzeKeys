"""Acceptance + security tests for secret versioning and environment rollback.

Runs against the FastAPI app via the authenticated test client (see conftest:
``authed_client`` is authenticated as ``test_user``). Covers append-only
versioning, single-secret and environment rollback, export, the no-plaintext
invariant on list endpoints, and the fail-closed (503) behaviour.
"""

import os

import pytest
from cryptography.fernet import Fernet


@pytest.fixture(autouse=True)
def credential_key():
    """Provide a valid Fernet key for the value-crypto paths.

    The service reads CREDENTIAL_ENCRYPTION_KEY lazily at call time, so setting
    it here is sufficient. Restored afterwards so the fixture is hermetic.
    """
    previous = os.environ.get("CREDENTIAL_ENCRYPTION_KEY")
    os.environ["CREDENTIAL_ENCRYPTION_KEY"] = Fernet.generate_key().decode()
    yield
    if previous is None:
        os.environ.pop("CREDENTIAL_ENCRYPTION_KEY", None)
    else:
        os.environ["CREDENTIAL_ENCRYPTION_KEY"] = previous


async def _create_env(client, name="Dev"):
    r = await client.post("/api/v1/secrets/environments", json={"name": name})
    assert r.status_code == 201, r.text
    return r.json()["id"]


async def _create_secret(client, env_id, key, value):
    r = await client.post(
        f"/api/v1/secrets/environments/{env_id}/secrets",
        json={"key": key, "value": value},
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


@pytest.mark.asyncio
async def test_version_history_is_append_only(authed_client):
    env_id = await _create_env(authed_client)
    sid = await _create_secret(authed_client, env_id, "DATABASE_URL", "v1val")

    # update twice
    for val in ("v2val", "v3val"):
        r = await authed_client.put(
            f"/api/v1/secrets/environments/{env_id}/secrets/{sid}",
            json={"value": val},
        )
        assert r.status_code == 200, r.text
    assert r.json()["current_version"] == 3

    # a no-op update (same value) does not append a version
    r = await authed_client.put(
        f"/api/v1/secrets/environments/{env_id}/secrets/{sid}",
        json={"value": "v3val"},
    )
    assert r.json()["current_version"] == 3

    # history has exactly 3 versions and NEVER exposes a decrypted value
    r = await authed_client.get(
        f"/api/v1/secrets/environments/{env_id}/secrets/{sid}/versions"
    )
    body = r.json()
    assert body["page"]["total"] == 3
    for item in body["items"]:
        assert "value" not in item


@pytest.mark.asyncio
async def test_single_secret_rollback_restores_old_value(authed_client):
    env_id = await _create_env(authed_client, "RollbackEnv")
    sid = await _create_secret(authed_client, env_id, "API_KEY", "k1")
    await authed_client.put(
        f"/api/v1/secrets/environments/{env_id}/secrets/{sid}", json={"value": "k2"}
    )

    # roll back to v1
    r = await authed_client.post(
        f"/api/v1/secrets/environments/{env_id}/secrets/{sid}/rollback",
        json={"version": 1},
    )
    assert r.status_code == 200, r.text
    assert r.json()["current_version"] == 3  # append-only: v3 carries v1's value

    # reveal current -> original value; history still intact
    r = await authed_client.post(
        f"/api/v1/secrets/environments/{env_id}/secrets/{sid}/reveal", json={}
    )
    assert r.status_code == 200, r.text
    assert r.json()["value"] == "k1"

    r = await authed_client.get(
        f"/api/v1/secrets/environments/{env_id}/secrets/{sid}/versions"
    )
    assert r.json()["page"]["total"] == 3


@pytest.mark.asyncio
async def test_reveal_specific_version(authed_client):
    env_id = await _create_env(authed_client, "RevealEnv")
    sid = await _create_secret(authed_client, env_id, "TOKEN", "first")
    await authed_client.put(
        f"/api/v1/secrets/environments/{env_id}/secrets/{sid}", json={"value": "second"}
    )
    r = await authed_client.post(
        f"/api/v1/secrets/environments/{env_id}/secrets/{sid}/reveal",
        json={"version": 1},
    )
    assert r.json()["value"] == "first"


@pytest.mark.asyncio
async def test_environment_rollback_restores_all_values(authed_client):
    env_id = await _create_env(authed_client, "FullEnv")
    a = await _create_secret(authed_client, env_id, "A", "a1")
    await _create_secret(authed_client, env_id, "B", "b1")

    # snapshot version after the two creates
    env = (await authed_client.get(f"/api/v1/secrets/environments/{env_id}")).json()
    good_snapshot = env["current_snapshot_version"]

    # change A
    await authed_client.put(
        f"/api/v1/secrets/environments/{env_id}/secrets/{a}", json={"value": "a2"}
    )

    # roll the whole environment back to the known-good snapshot
    r = await authed_client.post(
        f"/api/v1/secrets/environments/{env_id}/rollback",
        json={"snapshot_version": good_snapshot},
    )
    assert r.status_code == 200, r.text

    # export reflects the restored values
    r = await authed_client.get(f"/api/v1/secrets/environments/{env_id}/export")
    values = r.json()["values"]
    assert values == {"A": "a1", "B": "b1"}


@pytest.mark.asyncio
async def test_export_historical_snapshot(authed_client):
    env_id = await _create_env(authed_client, "HistEnv")
    sid = await _create_secret(authed_client, env_id, "X", "x1")
    env = (await authed_client.get(f"/api/v1/secrets/environments/{env_id}")).json()
    snap = env["current_snapshot_version"]
    await authed_client.put(
        f"/api/v1/secrets/environments/{env_id}/secrets/{sid}", json={"value": "x2"}
    )
    r = await authed_client.get(
        f"/api/v1/secrets/environments/{env_id}/export", params={"snapshot": snap}
    )
    assert r.json()["values"] == {"X": "x1"}


@pytest.mark.asyncio
async def test_secret_list_never_returns_values(authed_client):
    env_id = await _create_env(authed_client, "ListEnv")
    await _create_secret(authed_client, env_id, "SECRET_ONE", "super-secret-value")
    r = await authed_client.get(f"/api/v1/secrets/environments/{env_id}/secrets")
    body = r.json()
    assert body["page"]["total"] == 1
    assert "super-secret-value" not in r.text
    for item in body["items"]:
        assert "value" not in item


@pytest.mark.asyncio
async def test_bad_snapshot_rollback_404(authed_client):
    env_id = await _create_env(authed_client, "Bad404Env")
    r = await authed_client.post(
        f"/api/v1/secrets/environments/{env_id}/rollback",
        json={"snapshot_version": 9999},
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_missing_environment_404(authed_client):
    r = await authed_client.get("/api/v1/secrets/environments/424242")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_fail_closed_503_without_key(authed_client, monkeypatch):
    monkeypatch.delenv("CREDENTIAL_ENCRYPTION_KEY", raising=False)
    env_id = await _create_env(authed_client, "NoKeyEnv")  # env create needs no crypto
    r = await authed_client.post(
        f"/api/v1/secrets/environments/{env_id}/secrets",
        json={"key": "WILL_FAIL", "value": "x"},
    )
    assert r.status_code == 503
