"""Identity-backed signup paths enforce parent authority before any side effect."""

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.database import Base
from app.models.account import Account
from app.models.identity import Identity
from app.models.platform_identity import PlatformIdentity
from app.models.user import User
from app.routers import accounts, chat
from app.security import owner_authz
from app.security.platform_authz import PlatformAuthorizationUnavailable


@pytest.mark.asyncio
@pytest.mark.parametrize("path", ["direct-signup", "natural-language-signup"])
@pytest.mark.parametrize("decision", [True, False, "outage", "unlinked", "foreign"])
async def test_chat_signup_guard_precedes_log_or_response(monkeypatch, path, decision):
    row = SimpleNamespace(id=11, name="owned-identity")
    binding = SimpleNamespace(
        subject="verified-owner", tenant="tenant-a", verified_at=datetime.now()
    )
    rows = [
        SimpleNamespace(
            scalar_one_or_none=lambda: None if decision == "foreign" else row
        ),
        SimpleNamespace(
            scalar_one_or_none=lambda: None if decision == "unlinked" else binding
        ),
    ]
    db = SimpleNamespace(execute=AsyncMock(side_effect=rows))
    user = SimpleNamespace(id=7)
    check = AsyncMock(return_value=decision is True)
    if decision == "outage":
        check.side_effect = PlatformAuthorizationUnavailable()
    monkeypatch.setattr(owner_authz, "check_permission", check)
    log = Mock()
    monkeypatch.setattr(chat, "log_automation_event", log)
    if decision is True or (
        decision == "foreign" and path == "natural-language-signup"
    ):
        if path == "direct-signup":
            response = await chat.initiate_signup(
                chat.SignupRequest(website_url="https://example.test", identity_id=11),
                user,
                db,
            )
        else:
            response = await chat.chat_message(
                chat.ChatMessage(
                    message="sign me up for example.test with mine identity"
                ),
                user,
                db,
            )
        if decision is True:
            assert response.action_type == "automated_signup"
            log.assert_called_once()
            check.assert_awaited_once_with(
                "verified-owner",
                "tenant-a",
                "fuzekeys_Identity",
                "use",
                resource_key="identity:11",
            )
        else:
            assert response.action_type == "create_identity"
            check.assert_not_awaited()
            log.assert_not_called()
    else:
        with pytest.raises(HTTPException) as exc:
            if path == "direct-signup":
                await chat.initiate_signup(
                    chat.SignupRequest(
                        website_url="https://example.test", identity_id=11
                    ),
                    user,
                    db,
                )
            else:
                await chat.chat_message(
                    chat.ChatMessage(message="sign me up for example.test"), user, db
                )
        assert exc.value.status_code == (
            503 if decision == "outage" else 404 if decision == "foreign" else 403
        )
        log.assert_not_called()
    query = str(db.execute.await_args_list[0].args[0])
    assert "identities.user_id" in query


@pytest.mark.asyncio
@pytest.mark.parametrize("decision", [True, False, "outage", "foreign", "unlinked"])
async def test_account_creation_parent_use_and_persisted_denial(monkeypatch, decision):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    check = AsyncMock(return_value=decision is True)
    if decision == "outage":
        check.side_effect = PlatformAuthorizationUnavailable()
    monkeypatch.setattr(owner_authz, "check_permission", check)
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
            db.add_all([owner, foreign, Identity(id=11, user_id=7, name="owned")])
            if decision != "unlinked":
                db.add(
                    PlatformIdentity(
                        user_id=7,
                        subject="verified-owner",
                        tenant="tenant-a",
                        verified_at=datetime.now(),
                    )
                )
            await db.commit()
            body = accounts.AccountCreate(
                website_name="Example",
                website_url="https://example.test",
                identity_id=11,
            )
            if decision is True:
                response = await accounts.create_account(body, owner, db)
                assert response.identity_id == 11
                assert len((await db.execute(select(Account))).scalars().all()) == 1
                check.assert_awaited_once_with(
                    "verified-owner",
                    "tenant-a",
                    "fuzekeys_Identity",
                    "use",
                    resource_key="identity:11",
                )
            else:
                with pytest.raises(HTTPException) as exc:
                    await accounts.create_account(
                        body, foreign if decision == "foreign" else owner, db
                    )
                assert exc.value.status_code == (
                    503
                    if decision == "outage"
                    else 404
                    if decision == "foreign"
                    else 403
                )
                assert (await db.execute(select(Account))).scalars().all() == []
    finally:
        await engine.dispose()
