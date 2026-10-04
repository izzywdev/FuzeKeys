"""One Google credential per owner, with independent connector metadata."""

import json
from types import SimpleNamespace

import pytest
import pytest_asyncio
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.broker.vault import InMemoryVault
from app.models.connector import ConnectorCredential
from app.routers import connectors


@pytest_asyncio.fixture
async def google_custody(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(ConnectorCredential.__table__.create)
    vault = InMemoryVault()
    monkeypatch.setattr(connectors, "_vault", lambda: vault)
    async with AsyncSession(engine, expire_on_commit=False) as db:
        yield db, vault, SimpleNamespace(subject="owner/a")
    await engine.dispose()


def update(
    provider,
    *,
    subject="google-sub",
    client="client-id",
    refresh="refresh-1",
    scopes=None,
):
    credential = {
        "access_token": "access",
        "scope": " ".join(
            scopes
            or [
                connectors._GOOGLE_SCOPE_ROOT + name
                for name in connectors.GOOGLE_SCOPES[provider]
            ]
        ),
    }
    if refresh is not None:
        credential["refresh_token"] = refresh
    return connectors.CredentialUpdate(
        credential=credential,
        google_identity={"subject": subject, "client_id": client},
        configuration={"provider": provider},
    )


@pytest.mark.asyncio
async def test_shared_secret_preserves_refresh_and_independent_configuration(
    google_custody,
):
    db, vault, identity = google_custody
    scopes = [
        connectors._GOOGLE_SCOPE_ROOT + scope
        for scope in ("gmail.readonly", "drive.readonly")
    ]
    await connectors.update_credential(
        update(connectors.GMAIL, scopes=scopes), connectors.GMAIL, identity, db
    )
    await connectors.update_credential(
        update("google-drive", refresh=None, scopes=scopes),
        "google-drive",
        identity,
        db,
    )
    rows = (await db.execute(select(ConnectorCredential))).scalars().all()
    assert len(rows) == 2
    assert len({row.vault_ref for row in rows}) == 1
    assert rows[0].configuration != rows[1].configuration
    lease = await connectors.lease_credential("google-drive", identity, db)
    assert lease["credential"]["refresh_token"] == "refresh-1"
    assert lease["google_identity"] == {
        "subject": "google-sub",
        "client_id": "client-id",
    }
    await connectors.disconnect(connectors.GMAIL, identity, db)
    assert (
        vault.load_root(connectors._canonical_google_ref(identity.subject)) is not None
    )
    await connectors.disconnect("google-drive", identity, db)
    assert vault.load_root(connectors._canonical_google_ref(identity.subject)) is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "changes",
    [
        {"subject": "other-google"},
        {"client": "other-client"},
        {"scopes": [connectors._GOOGLE_SCOPE_ROOT + "drive.readonly"]},
    ],
)
async def test_mismatch_or_lost_grants_do_not_replace_existing_secret(
    google_custody, changes
):
    db, vault, identity = google_custody
    await connectors.update_credential(
        update(connectors.GMAIL), connectors.GMAIL, identity, db
    )
    ref = connectors._canonical_google_ref(identity.subject)
    before = vault.load_root(ref)
    with pytest.raises(HTTPException) as exc:
        await connectors.update_credential(
            update(connectors.GMAIL, **changes), connectors.GMAIL, identity, db
        )
    assert exc.value.status_code == 409
    assert vault.load_root(ref) == before


@pytest.mark.asyncio
async def test_legacy_gmail_requires_fresh_consent_to_bind(google_custody):
    db, vault, identity = google_custody
    ref = connectors._canonical_google_ref(identity.subject)
    vault.put(
        ref,
        json.dumps(
            {"access_token": "old-access", "refresh_token": "unverified-refresh"}
        ).encode(),
    )
    db.add(
        ConnectorCredential(
            owner_subject=identity.subject, provider=connectors.GMAIL, vault_ref=ref
        )
    )
    await db.commit()
    legacy = await connectors.lease_credential(connectors.GMAIL, identity, db)
    assert legacy["credential"]["refresh_token"] == "unverified-refresh"
    assert legacy["google_identity"] is None
    with pytest.raises(HTTPException):
        await connectors.update_credential(
            update(connectors.GMAIL, refresh=None), connectors.GMAIL, identity, db
        )
    await connectors.update_credential(
        update(connectors.GMAIL, refresh="fresh-consent"),
        connectors.GMAIL,
        identity,
        db,
    )
    lease = await connectors.lease_credential(connectors.GMAIL, identity, db)
    assert lease["credential"]["refresh_token"] == "fresh-consent"


@pytest.mark.asyncio
async def test_new_provider_cannot_replace_unverified_legacy_gmail_account(
    google_custody,
):
    db, vault, identity = google_custody
    ref = connectors._canonical_google_ref(identity.subject)
    legacy = b'{"access_token":"legacy-account","refresh_token":"legacy-refresh"}'
    vault.put(ref, legacy)
    db.add(
        ConnectorCredential(
            owner_subject=identity.subject, provider=connectors.GMAIL, vault_ref=ref
        )
    )
    await db.commit()
    scopes = [
        connectors._GOOGLE_SCOPE_ROOT + scope
        for scope in ("gmail.readonly", "drive.readonly")
    ]
    with pytest.raises(HTTPException) as exc:
        await connectors.update_credential(
            update("google-drive", subject="different-verified-account", scopes=scopes),
            "google-drive",
            identity,
            db,
        )
    assert exc.value.status_code == 409
    assert vault.load_root(ref) == legacy
    assert await connectors._record(db, identity.subject, "google-drive") is None
    # The owner can explicitly reconnect Gmail before enabling Drive.
    await connectors.update_credential(
        update(connectors.GMAIL, subject="different-verified-account", scopes=scopes),
        connectors.GMAIL,
        identity,
        db,
    )
    await connectors.update_credential(
        update(
            "google-drive",
            subject="different-verified-account",
            refresh=None,
            scopes=scopes,
        ),
        "google-drive",
        identity,
        db,
    )
    assert (await connectors.lease_credential("google-drive", identity, db))[
        "google_identity"
    ]["subject"] == "different-verified-account"


@pytest.mark.asyncio
async def test_separate_legacy_accounts_are_not_silently_combined(google_custody):
    db, vault, identity = google_custody
    ref = "connectors/owner%2Fa/google-drive"
    db.add(
        ConnectorCredential(
            owner_subject=identity.subject, provider="google-drive", vault_ref=ref
        )
    )
    vault.put(ref, b'{"access_token":"legacy"}')
    await db.commit()
    with pytest.raises(HTTPException) as exc:
        await connectors.update_credential(
            update(connectors.GMAIL), connectors.GMAIL, identity, db
        )
    assert exc.value.status_code == 409
    assert vault.load_root(ref) == b'{"access_token":"legacy"}'
    assert vault.load_root(connectors._canonical_google_ref(identity.subject)) is None


@pytest.mark.asyncio
async def test_owner_and_required_scope_boundaries(google_custody):
    db, vault, identity = google_custody
    await connectors.update_credential(
        update(connectors.GMAIL), connectors.GMAIL, identity, db
    )
    with pytest.raises(HTTPException) as exc:
        await connectors.lease_credential(
            connectors.GMAIL, SimpleNamespace(subject="other-owner"), db
        )
    assert exc.value.status_code == 404
    ref = connectors._canonical_google_ref(identity.subject)
    db.add(
        ConnectorCredential(
            owner_subject=identity.subject, provider="google-drive", vault_ref=ref
        )
    )
    await db.commit()
    with pytest.raises(HTTPException) as exc:
        await connectors.lease_credential("google-drive", identity, db)
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_google_binding_and_offline_token_required(google_custody):
    db, vault, identity = google_custody
    with pytest.raises(HTTPException):
        await connectors.update_credential(
            connectors.CredentialUpdate(credential={"access_token": "access"}),
            "google-drive",
            identity,
            db,
        )
    with pytest.raises(HTTPException):
        await connectors.update_credential(
            update(connectors.GMAIL, refresh=None), connectors.GMAIL, identity, db
        )
    assert vault.load_root(connectors._canonical_google_ref(identity.subject)) is None


@pytest.mark.asyncio
async def test_old_gmail_runtime_works_until_verified_binding_then_cannot_downgrade(
    google_custody,
):
    db, vault, identity = google_custody
    old_callback = connectors.CredentialUpdate(
        credential={"access_token": "old-callback", "refresh_token": "old-refresh"},
        identity_email="legacy@example.com",
    )
    await connectors.update_credential(old_callback, connectors.GMAIL, identity, db)
    lease = await connectors.lease_credential(connectors.GMAIL, identity, db)
    assert lease["credential"] == old_callback.credential
    assert lease["google_identity"] is None
    # Old runtime refreshes with a complete opaque credential blob.
    old_refresh = connectors.CredentialUpdate(
        credential={"access_token": "old-refreshed", "refresh_token": "old-refresh"}
    )
    await connectors.update_credential(old_refresh, connectors.GMAIL, identity, db)
    assert (await connectors.lease_credential(connectors.GMAIL, identity, db))[
        "credential"
    ] == old_refresh.credential
    with pytest.raises(HTTPException) as exc:
        await connectors.update_credential(old_refresh, "google-drive", identity, db)
    assert exc.value.status_code == 409
    await connectors.update_credential(
        update(connectors.GMAIL), connectors.GMAIL, identity, db
    )
    ref = connectors._canonical_google_ref(identity.subject)
    bound = vault.load_root(ref)
    with pytest.raises(HTTPException) as exc:
        await connectors.update_credential(old_callback, connectors.GMAIL, identity, db)
    assert exc.value.status_code == 409
    assert vault.load_root(ref) == bound


@pytest.mark.asyncio
async def test_postgres_group_lock_is_bound_and_stable():
    calls = []

    class Database:
        def get_bind(self):
            return SimpleNamespace(dialect=SimpleNamespace(name="postgresql"))

        async def execute(self, query, params):
            calls.append((str(query), params))

    db = Database()
    await connectors._lock_google(db, "owner/a")
    await connectors._lock_google(db, "owner/a")
    await connectors._lock_google(db, "owner/b")
    assert calls[0] == calls[1]
    assert calls[0][1] != calls[2][1]
    assert calls[0][0] == "SELECT pg_advisory_xact_lock(:key)"
