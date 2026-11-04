"""Legacy credential routes bind delegated callers to local owners and grants."""

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import HTTPException

from app.routers import credentials
from app.security import owner_authz
from app.security.fuzefront_auth import Identity as DelegatedIdentity
from app.security.platform_authz import PlatformAuthorizationUnavailable


def delegated(subject="owner", tenant="tenant-1", actor="service:scraper"):
    return DelegatedIdentity(
        subject=subject,
        tenant_id=tenant,
        scopes=frozenset(
            {"connectors:credentials:read", "connectors:credentials:write"}
        ),
        audience="service:fuzekeys",
        actor={"sub": actor},
        token_kind="fuze-delegation",
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "decision,expected",
    [
        (True, None),
        (False, 403),
        (1, 403),
        ("outage", 503),
        ("missing", 403),
        ("foreign-subject", 403),
        ("foreign-tenant", 403),
    ],
)
async def test_delegated_owner_requires_matching_binding_and_exact_allow(
    monkeypatch, decision, expected
):
    binding = SimpleNamespace(
        subject="other" if decision == "foreign-subject" else "owner",
        tenant="other" if decision == "foreign-tenant" else "tenant-1",
        verified_at=datetime.now(),
    )
    db = SimpleNamespace(
        execute=AsyncMock(
            return_value=SimpleNamespace(
                scalar_one_or_none=lambda: None if decision == "missing" else binding
            )
        )
    )
    check = AsyncMock(return_value=decision)
    if decision == "outage":
        check.side_effect = PlatformAuthorizationUnavailable()
    monkeypatch.setattr(owner_authz, "check_permission", check)

    if expected is None:
        await owner_authz.require_delegated_owner_permission(
            db, delegated(), 7, "Account", 21, "read"
        )
        check.assert_awaited_once_with(
            "owner",
            "tenant-1",
            "fuzekeys_Account",
            "read",
            resource_key="account:21",
        )
    else:
        with pytest.raises(HTTPException) as error:
            await owner_authz.require_delegated_owner_permission(
                db, delegated(), 7, "Account", 21, "read"
            )
        assert error.value.status_code == expected
        if decision in {"missing", "foreign-subject", "foreign-tenant"}:
            check.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["read", "write"])
async def test_credential_secret_operation_denies_before_crypto(monkeypatch, operation):
    owner = SimpleNamespace(id=11, user_id=7)
    db = SimpleNamespace(
        execute=AsyncMock(
            return_value=SimpleNamespace(scalar_one_or_none=lambda: owner)
        ),
        commit=AsyncMock(),
        rollback=AsyncMock(),
    )
    guard = AsyncMock(side_effect=HTTPException(403, "denied"))
    decrypt = Mock(side_effect=AssertionError("must not decrypt"))
    encrypt = Mock(side_effect=AssertionError("must not encrypt"))
    monkeypatch.setattr(credentials, "require_delegated_owner_permission", guard)
    monkeypatch.setattr(credentials, "decrypt_credential", decrypt)
    monkeypatch.setattr(credentials, "encrypt_credential", encrypt)

    with pytest.raises(HTTPException) as error:
        if operation == "read":
            await credentials.request_account_credentials(
                credentials.AccountCredentialRequest(
                    identity_id=11, account_id=21, credential_types=[]
                ),
                delegated(),
                db,
            )
        else:
            await credentials.store_account_credentials(
                credentials.CredentialUpdate(
                    identity_id=11,
                    account_id=21,
                    credentials={"password": "must-not-write"},
                ),
                delegated(),
                db,
            )
    assert error.value.status_code == 403
    assert db.execute.await_count == 1
    db.commit.assert_not_awaited()
    decrypt.assert_not_called()
    encrypt.assert_not_called()


def test_credential_routes_use_delegated_security_dependencies():
    route_dependencies = {}
    for route in credentials.router.routes:
        if route.path == "/api/credentials/health":
            continue
        route_dependencies[route.path] = {
            dependency.call
            for dependency in route.dependant.dependencies
            if dependency.call is not None
        }
    assert set(route_dependencies) == {
        "/api/credentials/request-identity-credentials",
        "/api/credentials/request-account-credentials",
        "/api/credentials/store-account-credentials",
        "/api/credentials/account/{account_id}/credentials",
        "/api/credentials/identity/{identity_id}/accounts",
        "/api/credentials/validate-credentials",
    }
    for dependencies in route_dependencies.values():
        assert credentials.verify_api_key not in dependencies
        assert any(
            getattr(dependency, "__name__", "") == "dependency"
            for dependency in dependencies
        )
