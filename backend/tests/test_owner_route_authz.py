"""Existing-row mutation guards through handlers, HTTP and persisted SQL state."""

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from app.routers import accounts, identities
from app.security import owner_authz
from app.security.platform_authz import PlatformAuthorizationUnavailable

CASES = ["identity-update", "identity-delete", "account-stage"]


def result(row):
    return SimpleNamespace(scalar_one_or_none=lambda: row)


async def invoke(case, db):
    user = SimpleNamespace(id=7)
    if case == "identity-update":
        return await identities.update_identity(
            11, identities.IdentityUpdate(name="changed"), user, db
        )
    if case == "identity-delete":
        return await identities.delete_identity(11, user, db)
    return await accounts.update_account_stage(
        11, 23, accounts.AccountStageUpdate(status="completed"), user, db
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("case", CASES)
@pytest.mark.parametrize(
    "decision", [True, False, "truthy", "outage", "unlinked", "unverified", "foreign"]
)
async def test_mutations_require_sql_owner_and_verified_instance_allow(
    monkeypatch, case, decision
):
    row = SimpleNamespace(
        id=11,
        account_id=11,
        name="original",
        status=accounts.StageStatus.PENDING,
        error_message=None,
        completed_at=None,
        attempts=0,
    )
    binding = SimpleNamespace(
        subject="verified-subject", tenant="tenant-1", verified_at=datetime.now()
    )
    if decision == "unverified":
        binding.verified_at = None
    rows = [
        result(None if decision == "foreign" else row),
        result(None if decision == "unlinked" else binding),
    ]
    db = SimpleNamespace(
        execute=AsyncMock(side_effect=rows),
        commit=AsyncMock(),
        refresh=AsyncMock(),
        delete=AsyncMock(),
    )
    # An integer one is truthy but is not an explicit boolean allow decision.
    check = AsyncMock(return_value=1 if decision == "truthy" else decision is True)
    if decision == "outage":
        check.side_effect = PlatformAuthorizationUnavailable()
    monkeypatch.setattr(owner_authz, "check_permission", check)
    monkeypatch.setattr(
        identities, "decrypt_identity_data", lambda value: {"id": value.id}
    )

    if decision is True:
        await invoke(case, db)
        db.commit.assert_awaited_once()
        if case == "identity-delete":
            db.delete.assert_awaited_once_with(row)
        elif case == "identity-update":
            assert row.name == "changed"
        else:
            assert row.status == accounts.StageStatus.COMPLETED
            assert row.attempts == 1
    else:
        with pytest.raises(HTTPException) as error:
            await invoke(case, db)
        expected = (
            503 if decision == "outage" else 404 if decision == "foreign" else 403
        )
        assert error.value.status_code == expected
        db.commit.assert_not_awaited()
        db.delete.assert_not_awaited()
        assert row.name == "original"
        assert row.status == accounts.StageStatus.PENDING
        assert row.attempts == 0

    # The platform guard cannot replace the local ownership predicate.
    sql = str(
        db.execute.call_args_list[0]
        .args[0]
        .compile(compile_kwargs={"literal_binds": True})
    )
    assert "identities.user_id = 7" in sql
    if case == "account-stage":
        assert "account_stages.account_id = 11" in sql
        assert "account_stages.id = 23" in sql
    else:
        assert "identities.id = 11" in sql

    if decision in ("foreign", "unlinked", "unverified"):
        check.assert_not_awaited()
    else:
        resource = "Account" if case == "account-stage" else "Identity"
        check.assert_awaited_once_with(
            "verified-subject",
            "tenant-1",
            "fuzekeys_" + resource,
            "delete" if case == "identity-delete" else "update",
            resource_key=resource.lower() + ":11",
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "resource,instance,action",
    [
        ("Site", 11, "update"),
        ("Identity", 0, "delete"),
        ("Identity", True, "update"),
        ("Account", 11, "create"),
    ],
)
async def test_guard_rejects_invalid_instance_queries_before_database(
    resource, instance, action
):
    db = SimpleNamespace(execute=AsyncMock())
    with pytest.raises(HTTPException) as error:
        await owner_authz.require_owner_permission(db, 7, resource, instance, action)
    assert error.value.status_code == 403
    db.execute.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("case", CASES)
@pytest.mark.parametrize(
    "decision,expected", [(True, 200), (False, 403), ("outage", 503), ("unlinked", 403)]
)
async def test_http_mutation_and_persisted_state(
    monkeypatch,
    case,
    decision,
    expected,
    authed_client,
    db_session,
    test_user,
    sample_identity,
    sample_account,
):
    """Exercise FastAPI and the real SQL rows, including rollback-free denial."""
    from sqlalchemy import select

    from app.models.account import AccountStage, StageType
    from app.models.identity import Identity
    from app.models.platform_identity import PlatformIdentity

    if decision != "unlinked":
        db_session.add(
            PlatformIdentity(
                user_id=test_user.id, subject="verified-owner", tenant="tenant-1"
            )
        )
    stage = AccountStage(
        account_id=sample_account.id,
        stage_type=StageType.PROFILE_SETUP,
        stage_name="Profile",
        status=accounts.StageStatus.PENDING,
    )
    db_session.add(stage)
    await db_session.commit()
    await db_session.refresh(stage)
    identity_id, account_id, stage_id = sample_identity.id, sample_account.id, stage.id
    check = AsyncMock(return_value=decision is True)
    if decision == "outage":
        check.side_effect = PlatformAuthorizationUnavailable()
    monkeypatch.setattr(owner_authz, "check_permission", check)

    if case == "identity-update":
        response = await authed_client.put(
            f"/api/v1/identities/{identity_id}", json={"name": "changed"}
        )
    elif case == "identity-delete":
        response = await authed_client.delete(f"/api/v1/identities/{identity_id}")
    else:
        response = await authed_client.patch(
            f"/api/v1/accounts/{account_id}/stages/{stage_id}",
            json={"status": "completed"},
        )
    assert response.status_code == expected, response.text
    identity = (
        await db_session.execute(select(Identity).where(Identity.id == identity_id))
    ).scalar_one_or_none()
    if case == "identity-delete" and decision is True:
        assert identity is None
    else:
        await db_session.refresh(identity)
        assert identity.name == (
            "changed"
            if case == "identity-update" and decision is True
            else "Test Identity"
        )
    if case == "account-stage":
        await db_session.refresh(stage)
        assert stage.status == (
            accounts.StageStatus.COMPLETED
            if decision is True
            else accounts.StageStatus.PENDING
        )
        assert stage.attempts == (1 if decision is True else 0)
    if decision == "unlinked":
        check.assert_not_awaited()
    else:
        resource = "Account" if case == "account-stage" else "Identity"
        instance = account_id if case == "account-stage" else identity_id
        check.assert_awaited_once_with(
            "verified-owner",
            "tenant-1",
            "fuzekeys_" + resource,
            "delete" if case == "identity-delete" else "update",
            resource_key=resource.lower() + ":" + str(instance),
        )
