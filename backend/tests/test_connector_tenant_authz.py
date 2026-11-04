"""Tenant-isolated custody, explicit pending enrollment and fail-closed decisions."""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
import pytest_asyncio
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.broker.vault import InMemoryVault
from app.models.connector import ConnectorCredential, ConnectorGrantIntent
from app.routers import connectors
from app.security import connector_authz
from app.security.platform_authz import PlatformAuthorizationUnavailable


@pytest_asyncio.fixture
async def custody(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(ConnectorCredential.__table__.create)
        await conn.run_sync(ConnectorGrantIntent.__table__.create)
    vault = InMemoryVault()
    monkeypatch.setattr(connectors, "_vault", lambda: vault)
    check = AsyncMock(return_value=True)
    monkeypatch.setattr(connector_authz, "check_permission", check)
    try:
        async with AsyncSession(engine, expire_on_commit=False) as db:
            yield db, vault, check, SimpleNamespace(
                subject="owner", tenant_id="tenant-a"
            )
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_enrollment_stages_only_owned_nonsecret_metadata_then_checked_retry(
    custody,
):
    db, vault, check, identity = custody
    body = connectors.CredentialUpdate(
        credential={"token": "private-token"},
        identity_email="private-email@example.test",
        scopes=["secret-scope"],
        configuration={"private": "request-data"},
    )
    response = await connectors.update_credential(body, "slack", identity, db)
    assert response.status_code == 202
    assert json.loads(response.body)["status"] == "authorization_pending"
    row = (await db.execute(select(ConnectorCredential))).scalar_one()
    intent = (await db.execute(select(ConnectorGrantIntent))).scalar_one()
    assert row.tenant_id == identity.tenant_id and row.owner_subject == identity.subject
    assert row.identity_email is None and row.scopes == [] and row.configuration == {}
    assert intent.desired_state == "present"
    assert intent.resource_key == connector_authz.connector_resource_key(
        identity.tenant_id, identity.subject, "slack"
    )
    assert vault.load_root(row.vault_ref) is None
    check.assert_not_awaited()
    assert await connectors.update_credential(body, "slack", identity, db) == {
        "status": "updated"
    }
    assert json.loads(vault.load_root(row.vault_ref)) == {"token": "private-token"}
    assert [call.args[3] for call in check.await_args_list] == [
        "create",
        "write_credential",
    ]
    assert all(
        call.args[:3] == ("owner", "tenant-a", "fuzekeys_Connector")
        for call in check.await_args_list
    )
    await connectors.disconnect("slack", identity, db)
    assert intent.desired_state == "absent"
    assert vault.load_root(row.vault_ref) is None


@pytest.mark.asyncio
@pytest.mark.parametrize("decision", [False, 1, "outage"])
@pytest.mark.parametrize(
    "operation", ["write", "configure", "disconnect", "reveal", "status"]
)
async def test_denial_never_reads_writes_or_deletes_vault(
    custody, monkeypatch, decision, operation
):
    db, vault, check, identity = custody
    body = connectors.CredentialUpdate(credential={"token": "private-token"})
    await connectors.update_credential(body, "slack", identity, db)
    check.return_value = decision
    if decision == "outage":
        check.side_effect = PlatformAuthorizationUnavailable()
    forbidden = Mock(side_effect=AssertionError("denied operation reached vault"))
    monkeypatch.setattr(connectors, "_vault", forbidden)
    with pytest.raises(HTTPException) as exc:
        if operation == "write":
            await connectors.update_credential(body, "slack", identity, db)
        elif operation == "configure":
            await connectors.configure("slack", {"x": 1}, identity, db)
        elif operation == "disconnect":
            await connectors.disconnect("slack", identity, db)
        elif operation == "reveal":
            await connectors.lease_credential("slack", identity, db)
        else:
            await connectors.status("slack", identity, db)
    assert exc.value.status_code == (503 if decision == "outage" else 403)
    forbidden.assert_not_called()
    row = (await db.execute(select(ConnectorCredential))).scalar_one()
    assert row.status == "authorization_pending" and row.configuration == {}


@pytest.mark.asyncio
async def test_unbound_legacy_row_cannot_be_borrowed_or_tenant_guessed(custody):
    db, vault, check, identity = custody
    legacy = ConnectorCredential(
        owner_subject=identity.subject,
        provider="slack",
        vault_ref="legacy/path",
        status="connected",
    )
    db.add(legacy)
    await db.commit()
    vault.put("legacy/path", b'{"token":"old-secret"}')
    assert (await connectors.status("slack", identity, db))["status"] == "disconnected"
    with pytest.raises(HTTPException) as exc:
        await connectors.lease_credential("slack", identity, db)
    assert exc.value.status_code == 404
    await connectors.update_credential(
        connectors.CredentialUpdate(credential={"token": "fresh-secret"}),
        "slack",
        identity,
        db,
    )
    assert legacy.tenant_id is None
    assert vault.load_root("legacy/path") == b'{"token":"old-secret"}'
    check.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("tenant", [None, "", " tenant-a", 1])
async def test_missing_verified_tenant_cannot_even_stage(custody, tenant):
    db, vault, check, identity = custody
    with pytest.raises(HTTPException) as exc:
        await connectors.update_credential(
            connectors.CredentialUpdate(credential={"token": "secret"}),
            "slack",
            SimpleNamespace(subject="owner", tenant_id=tenant),
            db,
        )
    assert exc.value.status_code == 403
    assert (await db.execute(select(ConnectorCredential))).scalars().all() == []
    check.assert_not_awaited()


@pytest.mark.asyncio
async def test_google_shared_refcounts_and_locks_do_not_cross_tenant(custody):
    db, vault, check, identity = custody
    other = SimpleNamespace(subject=identity.subject, tenant_id="tenant-b")
    body = connectors.CredentialUpdate(
        credential={
            "access_token": "access",
            "refresh_token": "refresh",
            "scope": "https://www.googleapis.com/auth/gmail.readonly",
        },
        google_identity={"subject": "google-account", "client_id": "client"},
    )
    for caller in (identity, other):
        staged = await connectors.update_credential(body, connectors.GMAIL, caller, db)
        assert staged.status_code == 202
        await connectors.update_credential(body, connectors.GMAIL, caller, db)
    assert connectors._canonical_google_ref(
        identity.tenant_id, identity.subject
    ) != connectors._canonical_google_ref(other.tenant_id, other.subject)
    await connectors.disconnect(connectors.GMAIL, identity, db)
    assert (await connectors.lease_credential(connectors.GMAIL, other, db))[
        "credential"
    ]["refresh_token"] == "refresh"
    calls = []
    fake_db = SimpleNamespace(
        get_bind=lambda: SimpleNamespace(dialect=SimpleNamespace(name="postgresql")),
        execute=AsyncMock(side_effect=lambda query, params: calls.append(params)),
    )
    await connectors._lock_google(fake_db, identity.tenant_id, identity.subject)
    await connectors._lock_google(fake_db, other.tenant_id, other.subject)
    assert calls[0] != calls[1]
