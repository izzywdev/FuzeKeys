"""Google identity operations deny before browser automation or PII conversion."""

import json
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import HTTPException

from app.routers import google_integration
from app.security import owner_authz
from app.security.platform_authz import PlatformAuthorizationUnavailable


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "operation,action", [("signup", "use"), ("conversion", "read")]
)
@pytest.mark.parametrize(
    "decision", [True, False, "truthy", "outage", "unlinked", "unverified", "foreign"]
)
async def test_identity_operations_decide_before_effects(
    monkeypatch, operation, action, decision
):
    row = SimpleNamespace(id=11, user_id=7)
    binding = SimpleNamespace(
        subject="verified-subject", tenant="tenant-1", verified_at=datetime.now()
    )
    if decision == "unverified":
        binding.verified_at = None
    db = SimpleNamespace(
        execute=AsyncMock(
            side_effect=[
                SimpleNamespace(
                    scalar_one_or_none=lambda: None if decision == "foreign" else row
                ),
                SimpleNamespace(
                    scalar_one_or_none=lambda: None
                    if decision == "unlinked"
                    else binding
                ),
            ]
        ),
        add=Mock(),
        commit=AsyncMock(),
        refresh=AsyncMock(),
    )
    check = AsyncMock(return_value=1 if decision == "truthy" else decision is True)
    if decision == "outage":
        check.side_effect = PlatformAuthorizationUnavailable()
    monkeypatch.setattr(owner_authz, "check_permission", check)
    service = SimpleNamespace(
        signup_with_identity=AsyncMock(
            return_value=SimpleNamespace(
                success=False,
                account_email=None,
                error_message="verification needed",
                verification_required=True,
                verification_type="phone",
            )
        ),
        _identity_to_signup_data=AsyncMock(
            return_value=SimpleNamespace(
                first_name="Test",
                last_name="User",
                username="testuser",
                password="private",
                phone_number=None,
                recovery_email=None,
                birth_date=None,
                gender=None,
            )
        ),
    )
    factory = Mock(return_value=service)
    monkeypatch.setattr(google_integration, "GoogleSignupService", factory)
    user = SimpleNamespace(id=7)

    async def invoke():
        if operation == "signup":
            return await google_integration.signup_with_identity(
                11, current_user=user, db=db
            )
        return await google_integration.test_identity_conversion(
            11, current_user=user, db=db
        )

    if decision is True:
        response = await invoke()
        factory.assert_called_once()
        if operation == "signup":
            service.signup_with_identity.assert_awaited_once_with(row)
        else:
            service._identity_to_signup_data.assert_awaited_once_with(row)
            assert response["signup_data"]["has_password"] is True
            assert "password" not in response["signup_data"]
    else:
        with pytest.raises(HTTPException) as caught:
            await invoke()
        expected = (
            503 if decision == "outage" else 404 if decision == "foreign" else 403
        )
        assert caught.value.status_code == expected
        factory.assert_not_called()
        service.signup_with_identity.assert_not_awaited()
        service._identity_to_signup_data.assert_not_awaited()
        db.add.assert_not_called()
        db.commit.assert_not_awaited()
        db.refresh.assert_not_awaited()

    sql = str(
        db.execute.call_args_list[0]
        .args[0]
        .compile(compile_kwargs={"literal_binds": True})
    )
    assert "identities.id = 11" in sql
    assert "identities.user_id = 7" in sql
    if decision == "foreign":
        check.assert_not_awaited()
        assert db.execute.await_count == 1
    elif decision not in ("unlinked", "unverified"):
        check.assert_awaited_once_with(
            "verified-subject",
            "tenant-1",
            "fuzekeys_Identity",
            action,
            resource_key="identity:11",
        )


@pytest.mark.asyncio
async def test_use_action_cannot_be_applied_to_account(monkeypatch):
    db = SimpleNamespace(execute=AsyncMock())
    check = AsyncMock()
    monkeypatch.setattr(owner_authz, "check_permission", check)
    with pytest.raises(HTTPException) as caught:
        await owner_authz.require_owner_permission(db, 7, "Account", 11, "use")
    assert caught.value.status_code == 403
    db.execute.assert_not_awaited()
    check.assert_not_awaited()


def test_identity_use_is_instance_role_and_chart_policy_matches():
    root = Path(google_integration.__file__).resolve().parents[3]
    policy = (root / "registration/policy.json").read_text()
    assert (
        policy
        == (root / "deploy/helm/fuzekeys/files/registration/policy.json").read_text()
    )
    declaration = json.loads(policy)
    identity = next(r for r in declaration["resources"] if r["key"] == "Identity")
    assert "use" in identity["actions"]
    assert "use" in identity["roles"]["owner"]["permissions"]
    for role in declaration["roles"]:
        assert "Identity:use" not in role["permissions"]


@pytest.mark.asyncio
async def test_successful_signup_persists_actual_schema_and_reads_scoped_accounts(
    monkeypatch,
):
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    from app.database import Base
    from app.models.account import Account
    from app.models.identity import Identity
    from app.models.platform_identity import PlatformIdentity
    from app.models.user import User
    from app.utils import encryption

    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    manager = encryption.EncryptionManager("test-google-owner-master")
    monkeypatch.setattr(encryption, "_global_encryption_manager", manager)
    result = SimpleNamespace(
        success=True,
        account_email="owner@example.com",
        account_id="provider-id",
        verification_required=False,
        verification_type=None,
        additional_data={"provider": "google"},
    )
    service = SimpleNamespace(signup_with_identity=AsyncMock(return_value=result))
    monkeypatch.setattr(
        google_integration, "GoogleSignupService", Mock(return_value=service)
    )
    check = AsyncMock(return_value=True)
    monkeypatch.setattr(owner_authz, "check_permission", check)
    try:
        async with AsyncSession(engine, expire_on_commit=False) as db:
            user = User(
                id=7,
                username="owner",
                email="owner@example.com",
                hashed_password="hash",
                master_key_hash="hash",
            )
            identity = Identity(id=11, user_id=7, name="Owner")
            db.add_all(
                [
                    user,
                    identity,
                    PlatformIdentity(
                        user_id=7,
                        subject="verified-subject",
                        tenant="tenant-1",
                        verified_at=datetime.now(),
                    ),
                ]
            )
            await db.commit()
            response = await google_integration.signup_with_identity(
                11, current_user=user, db=db
            )
            stored = (await db.execute(select(Account))).scalar_one()
            assert response["account_id"] == stored.id
            assert stored.website_name == "Google"
            assert stored.website_url == "https://accounts.google.com"
            assert stored.website_domain == "google.com"
            assert stored.signup_completed is True
            assert stored.signup_method == "automated"
            assert stored.encrypted_email != "owner@example.com"
            assert manager.decrypt(stored.encrypted_email) == "owner@example.com"
            assert (
                manager.decrypt_json(stored.encrypted_notes)["account_id"]
                == "provider-id"
            )
            check.reset_mock()
            listed = await google_integration.get_google_accounts(
                11, current_user=user, db=db
            )
            assert listed["accounts"][0]["email"] == "owner@example.com"
            assert listed["accounts"][0]["status"] == "active"
            assert listed["accounts"][0]["metadata"]["account_id"] == "provider-id"
            assert [c.args[2:] for c in check.await_args_list] == [
                ("fuzekeys_Identity", "read"),
                ("fuzekeys_Account", "read"),
            ]
            assert check.await_args_list[1].kwargs == {
                "resource_key": f"account:{stored.id}"
            }
            # A denied account cannot disclose even already-owned/decryptable PII.
            check.side_effect = [True, False]
            decrypt = Mock(side_effect=AssertionError("must not decrypt denied row"))
            monkeypatch.setattr(google_integration, "decrypt_field", decrypt)
            with pytest.raises(HTTPException) as denied:
                await google_integration.get_google_accounts(
                    11, current_user=user, db=db
                )
            assert denied.value.status_code == 403
            decrypt.assert_not_called()
    finally:
        await engine.dispose()
