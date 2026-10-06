"""Legacy credential APIs use the production AsyncSession transaction contract."""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from cryptography.fernet import Fernet
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.database import Base
from app.models.account import Account
from app.models.identity import Identity
from app.models.user import User
from app.routers import credentials
from app.security.fuzefront_auth import Identity as DelegatedIdentity

DELEGATED = DelegatedIdentity(
    subject="owner",
    tenant_id="tenant-1",
    scopes=frozenset({"connectors:credentials:read", "connectors:credentials:write"}),
    audience="service:fuzekeys",
    actor={"sub": "service:scraper"},
    token_kind="fuze-delegation",
)


@pytest.mark.asyncio
async def test_async_store_retrieve_generation_and_bounded_list(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    monkeypatch.setattr(credentials, "require_delegated_owner_permission", AsyncMock())
    monkeypatch.setattr(credentials, "ENCRYPTION_KEY", Fernet.generate_key().decode())
    try:
        async with AsyncSession(engine, expire_on_commit=False) as db:
            db.add_all(
                [
                    User(
                        id=7,
                        username="owner",
                        email="owner@example.com",
                        hashed_password="hash",
                        master_key_hash="hash",
                    ),
                    Identity(id=11, user_id=7, name="Owner Name"),
                    Identity(id=12, user_id=7, name="Other Identity"),
                    Account(
                        id=21,
                        identity_id=11,
                        website_name="Site A",
                        website_url="https://a.example",
                    ),
                    Account(
                        id=22,
                        identity_id=11,
                        website_name="Site B",
                        website_url="https://b.example",
                    ),
                    Account(
                        id=23,
                        identity_id=12,
                        website_name="Foreign",
                        website_url="https://foreign.example",
                    ),
                ]
            )
            await db.commit()
            # New encrypted credentials on an existing owned row, then update.
            for value in ["first-value", "updated-value"]:
                result = await credentials.store_account_credentials(
                    credentials.CredentialUpdate(
                        identity_id=11, account_id=21, credentials={"password": value}
                    ),
                    DELEGATED,
                    db,
                )
                assert result["success"] is True
                stored = await db.get(Account, 21)
                assert stored.encrypted_credentials != value
                assert (
                    json.loads(
                        credentials.decrypt_credential(stored.encrypted_credentials)
                    )["password"]
                    == value
                )
                assert stored.signup_completed is True
            read = await credentials.request_account_credentials(
                credentials.AccountCredentialRequest(
                    identity_id=11, account_id=21, credential_types=["password"]
                ),
                DELEGATED,
                db,
            )
            assert read.credentials == {"password": "updated-value"}
            assert read.last_used is not None
            stored = await db.get(Account, 21)
            assert stored.last_accessed is not None
            alias = await credentials.get_account_credentials(
                account_id=21,
                identity_id=11,
                credential_types="password",
                delegated_identity=DELEGATED,
                db=db,
            )
            assert alias.credentials == read.credentials
            generated = await credentials.request_identity_credentials(
                credentials.CredentialRequest(
                    identity_id=11,
                    site_name="github",
                    action_type="signup",
                    credential_types=["password"],
                ),
                DELEGATED,
                db,
            )
            assert set(generated.credentials) == {"password"}
            assert len(generated.credentials["password"]) >= 20
            listed = await credentials.get_identity_accounts(
                identity_id=11,
                limit=1,
                offset=1,
                delegated_identity=DELEGATED,
                db=db,
            )
            assert listed.page.total == 2
            assert listed.page.next_offset is None
            assert [item["account_id"] for item in listed.items] == [22]
            with pytest.raises(HTTPException) as mismatch:
                await credentials.store_account_credentials(
                    credentials.CredentialUpdate(
                        identity_id=11,
                        account_id=23,
                        credentials={"password": "must-not-write"},
                    ),
                    DELEGATED,
                    db,
                )
            assert mismatch.value.status_code == 404
            foreign = await db.get(Account, 23)
            assert foreign.encrypted_credentials is None
    finally:
        await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["store", "retrieve"])
async def test_commit_failure_rolls_back_and_reports_failure(monkeypatch, operation):
    monkeypatch.setattr(credentials, "require_delegated_owner_permission", AsyncMock())
    monkeypatch.setattr(credentials, "ENCRYPTION_KEY", Fernet.generate_key().decode())
    row = SimpleNamespace(
        id=21,
        identity_id=11,
        website_name="Site",
        encrypted_credentials=None,
        last_accessed=None,
        is_active=True,
        signup_completed=False,
    )
    owner = SimpleNamespace(id=11, user_id=7)
    db = SimpleNamespace(
        execute=AsyncMock(
            side_effect=[
                SimpleNamespace(scalar_one_or_none=lambda: owner),
                SimpleNamespace(scalar_one_or_none=lambda: row),
            ]
        ),
        commit=AsyncMock(side_effect=RuntimeError("transaction failed")),
        rollback=AsyncMock(),
    )
    with pytest.raises(HTTPException) as failed:
        if operation == "store":
            await credentials.store_account_credentials(
                credentials.CredentialUpdate(
                    identity_id=11, account_id=21, credentials={"password": "value"}
                ),
                DELEGATED,
                db,
            )
        else:
            await credentials.request_account_credentials(
                credentials.AccountCredentialRequest(
                    identity_id=11, account_id=21, credential_types=[]
                ),
                DELEGATED,
                db,
            )
    assert failed.value.status_code == 500
    db.commit.assert_awaited_once()
    db.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_out_of_scope_denies_before_sql_or_crypto(monkeypatch):
    guard = AsyncMock(side_effect=HTTPException(403, "denied"))
    monkeypatch.setattr(credentials, "require_delegated_owner_permission", guard)
    owner = SimpleNamespace(id=12, user_id=7)
    db = SimpleNamespace(
        execute=AsyncMock(
            return_value=SimpleNamespace(scalar_one_or_none=lambda: owner)
        ),
        commit=AsyncMock(),
    )
    decrypt = Mock(side_effect=AssertionError("must not decrypt"))
    encrypt = Mock(side_effect=AssertionError("must not encrypt"))
    monkeypatch.setattr(credentials, "decrypt_credential", decrypt)
    monkeypatch.setattr(credentials, "encrypt_credential", encrypt)
    for operation in ("store", "retrieve"):
        with pytest.raises(HTTPException) as denied:
            if operation == "store":
                await credentials.store_account_credentials(
                    credentials.CredentialUpdate(
                        identity_id=12, account_id=23, credentials={"password": "value"}
                    ),
                    DELEGATED,
                    db,
                )
            else:
                await credentials.request_account_credentials(
                    credentials.AccountCredentialRequest(
                        identity_id=12, account_id=23, credential_types=[]
                    ),
                    DELEGATED,
                    db,
                )
        assert denied.value.status_code == 403
    assert db.execute.await_count == 2
    db.commit.assert_not_awaited()
    decrypt.assert_not_called()
    encrypt.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["store", "retrieve"])
async def test_real_session_transaction_failure_leaves_persisted_values_unchanged(
    monkeypatch, operation
):
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    monkeypatch.setattr(credentials, "require_delegated_owner_permission", AsyncMock())
    monkeypatch.setattr(credentials, "ENCRYPTION_KEY", Fernet.generate_key().decode())
    try:
        async with AsyncSession(engine, expire_on_commit=False) as db:
            db.add_all(
                [
                    User(
                        id=7,
                        username="owner",
                        email="owner@example.com",
                        hashed_password="hash",
                        master_key_hash="hash",
                    ),
                    Identity(id=11, user_id=7, name="Owner"),
                    Account(
                        id=21,
                        identity_id=11,
                        website_name="Site",
                        website_url="https://site.example",
                        encrypted_credentials=None,
                    ),
                ]
            )
            await db.commit()
            monkeypatch.setattr(
                db, "commit", AsyncMock(side_effect=RuntimeError("commit failure"))
            )
            with pytest.raises(HTTPException) as failed:
                if operation == "store":
                    await credentials.store_account_credentials(
                        credentials.CredentialUpdate(
                            identity_id=11,
                            account_id=21,
                            credentials={"password": "must-not-persist"},
                        ),
                        DELEGATED,
                        db,
                    )
                else:
                    await credentials.request_account_credentials(
                        credentials.AccountCredentialRequest(
                            identity_id=11, account_id=21, credential_types=[]
                        ),
                        DELEGATED,
                        db,
                    )
            assert failed.value.status_code == 500
            row = await db.get(Account, 21)
            assert row.encrypted_credentials is None
            assert row.last_accessed is None
            assert row.signup_completed is False
    finally:
        await engine.dispose()
