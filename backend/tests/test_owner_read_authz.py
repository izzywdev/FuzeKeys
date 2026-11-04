"""Owned read responses require exact instance allows before PII projection."""

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import HTTPException

from app.routers import accounts, identities
from app.security import owner_authz
from app.security.platform_authz import PlatformAuthorizationUnavailable


@pytest.mark.asyncio
@pytest.mark.parametrize("family", ["identity-detail", "identity-list", "account-list"])
@pytest.mark.parametrize("decision", [True, False, "outage", "unlinked", "truthy"])
async def test_read_requires_exact_allow_before_response(monkeypatch, family, decision):
    row = SimpleNamespace(id=11, identity_id=17)
    binding = SimpleNamespace(
        subject="owner", tenant="tenant", verified_at=datetime.now()
    )
    scalar = SimpleNamespace(scalar_one_or_none=lambda: row)
    count = SimpleNamespace(scalar_one=lambda: 1)
    page = SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: [row]))
    linked = SimpleNamespace(
        scalar_one_or_none=lambda: None if decision == "unlinked" else binding
    )
    db = SimpleNamespace(
        execute=AsyncMock(
            side_effect=([scalar] if family == "identity-detail" else [count, page])
            + [linked, linked]
        )
    )
    check = AsyncMock(return_value=1 if decision == "truthy" else decision is True)
    if decision == "outage":
        check.side_effect = PlatformAuthorizationUnavailable()
    monkeypatch.setattr(owner_authz, "check_permission", check)
    # Response construction stands in for any read/decryption of protected fields.
    projection = Mock(return_value={"id": 11})
    target = identities if family.startswith("identity") else accounts
    monkeypatch.setattr(
        target,
        "decrypt_identity_data"
        if family == "identity-detail"
        else "IdentityListResponse"
        if family == "identity-list"
        else "AccountResponse",
        projection,
    )
    row.name = "owner identity"
    row.description = None
    row.created_at = datetime.now()
    row.website_name = "provider"
    row.website_url = "https://example.test"
    row.identity = SimpleNamespace(name="parent")
    row.is_active = True
    row.signup_completed = False
    row.stages = []
    user = SimpleNamespace(id=7)
    if decision is True:
        if family == "identity-detail":
            response = await identities.get_identity(11, user, db)
            assert response == {"id": 11}
        else:
            handler = (
                identities.list_identities
                if family == "identity-list"
                else accounts.list_accounts
            )
            response = await handler(50, 0, user, db)
            assert response.page.total == 1
        projection.assert_called_once()
    else:
        with pytest.raises(HTTPException) as caught:
            if family == "identity-detail":
                await identities.get_identity(11, user, db)
            else:
                handler = (
                    identities.list_identities
                    if family == "identity-list"
                    else accounts.list_accounts
                )
                await handler(50, 0, user, db)
        assert caught.value.status_code == (503 if decision == "outage" else 403)
        projection.assert_not_called()
    if decision == "unlinked":
        check.assert_not_awaited()
    else:
        check.assert_any_await(
            "owner",
            "tenant",
            "fuzekeys_Account" if family == "account-list" else "fuzekeys_Identity",
            "read",
            resource_key="account:11" if family == "account-list" else "identity:11",
        )
        if family == "account-list" and decision is True:
            check.assert_any_await(
                "owner",
                "tenant",
                "fuzekeys_Identity",
                "read",
                resource_key="identity:17",
            )


@pytest.mark.asyncio
async def test_foreign_identity_is_not_decrypted_or_authorized(monkeypatch):
    db = SimpleNamespace(
        execute=AsyncMock(return_value=SimpleNamespace(scalar_one_or_none=lambda: None))
    )
    check = AsyncMock()
    decrypt = Mock()
    monkeypatch.setattr(owner_authz, "check_permission", check)
    monkeypatch.setattr(identities, "decrypt_identity_data", decrypt)
    with pytest.raises(HTTPException) as caught:
        await identities.get_identity(11, SimpleNamespace(id=7), db)
    assert caught.value.status_code == 404
    check.assert_not_awaited()
    decrypt.assert_not_called()
    query = str(db.execute.await_args.args[0])
    assert "identities.user_id" in query
    assert "identities.id" in query


@pytest.mark.asyncio
@pytest.mark.parametrize("family", ["identity-list", "account-list"])
async def test_later_denied_row_prevents_entire_page_projection(monkeypatch, family):
    rows = [
        SimpleNamespace(id=11, identity_id=17),
        SimpleNamespace(id=12, identity_id=18),
    ]
    count = SimpleNamespace(scalar_one=lambda: 2)
    page = SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: rows))
    binding = SimpleNamespace(
        scalar_one_or_none=lambda: SimpleNamespace(
            subject="owner", tenant="tenant", verified_at=datetime.now()
        )
    )
    db = SimpleNamespace(execute=AsyncMock(side_effect=[count, page] + [binding] * 4))
    check = AsyncMock(
        side_effect=[True, False] if family == "identity-list" else [True, True, False]
    )
    monkeypatch.setattr(owner_authz, "check_permission", check)
    projection = Mock()
    module = identities if family == "identity-list" else accounts
    monkeypatch.setattr(
        module,
        "IdentityListResponse" if family == "identity-list" else "AccountResponse",
        projection,
    )
    with pytest.raises(HTTPException) as caught:
        await (
            identities.list_identities
            if family == "identity-list"
            else accounts.list_accounts
        )(50, 0, SimpleNamespace(id=7), db)
    assert caught.value.status_code == 403
    projection.assert_not_called()
    for call in db.execute.await_args_list[:2]:
        assert "identities.user_id" in str(call.args[0])


@pytest.mark.asyncio
async def test_sql_owner_filter_and_scoped_page_with_real_rows(monkeypatch):
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    from app.database import Base
    from app.models.identity import Identity
    from app.models.platform_identity import PlatformIdentity
    from app.models.user import User

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    check = AsyncMock(return_value=True)
    monkeypatch.setattr(owner_authz, "check_permission", check)
    decrypt = Mock(return_value={"id": 11})
    monkeypatch.setattr(identities, "decrypt_identity_data", decrypt)
    try:
        async with AsyncSession(engine, expire_on_commit=False) as db:
            owner = User(
                id=7,
                username="owner",
                email="owner@example.test",
                hashed_password="hash",
                master_key_hash="hash",
            )
            foreign = User(
                id=8,
                username="foreign",
                email="foreign@example.test",
                hashed_password="hash",
                master_key_hash="hash",
            )
            db.add_all(
                [
                    owner,
                    foreign,
                    Identity(id=11, user_id=7, name="own"),
                    Identity(id=12, user_id=8, name="foreign"),
                    PlatformIdentity(
                        user_id=7,
                        subject="owner",
                        tenant="tenant",
                        verified_at=datetime.now(),
                    ),
                ]
            )
            await db.commit()
            page = await identities.list_identities(50, 0, owner, db)
            assert [item.id for item in page.items] == [11]
            assert page.page.total == 1
            check.assert_awaited_once_with(
                "owner",
                "tenant",
                "fuzekeys_Identity",
                "read",
                resource_key="identity:11",
            )
            check.reset_mock()
            with pytest.raises(HTTPException) as foreign_error:
                await identities.get_identity(12, owner, db)
            assert foreign_error.value.status_code == 404
            check.assert_not_awaited()
            decrypt.assert_not_called()
            check.return_value = False
            with pytest.raises(HTTPException) as denial:
                await identities.get_identity(11, owner, db)
            assert denial.value.status_code == 403
            decrypt.assert_not_called()
    finally:
        await engine.dispose()
