"""Tests for the FuzeFront Security integration.

These cover the two properties that matter most about delegating auth:

  1. FuzeKeys asks FuzeFront who the caller is and never decides for itself —
     no local signing key, no local password, no local policy evaluation.
  2. Every failure mode is a DENIAL. An unreachable security service, a
     malformed response, a missing tenant, a length-mismatched bulk decision:
     all fail closed. An authorization layer that opens when it breaks is
     worse than none, because it is trusted.

The security service is stubbed with an httpx MockTransport rather than a
network call, so the assertions are about OUR behaviour at each contract
boundary, not about a live FuzeFront.
"""

import json

import httpx
import pytest

from app.security.client import (
    FuzeFrontSecurityClient,
    SecurityError,
)
from app.security.contract import AuthzCheck, Identity


# ── helpers ───────────────────────────────────────────────────────────────────
SESSION_BODY = {
    "identity": {
        "userId": "ff-subject-123",
        "tenantId": "tenant-abc",
        "roles": ["operator"],
        "authMode": "federated-jwks",
        "email": "user@example.test",
    },
    "user": {
        "id": "ff-subject-123",
        "email": "user@example.test",
        "firstName": "Ada",
        "lastName": "Lovelace",
        "roles": ["operator"],
    },
}


def _client(handler) -> FuzeFrontSecurityClient:
    return FuzeFrontSecurityClient(
        base_url="http://security.test",
        transport=httpx.MockTransport(handler),
    )


# ── contract parsing ─────────────────────────────────────────────────────────
def test_identity_parses_session_info():
    identity = Identity.from_session_info(SESSION_BODY)
    assert identity.user_id == "ff-subject-123"
    assert identity.tenant_id == "tenant-abc"
    assert identity.roles == ["operator"]
    assert identity.email == "user@example.test"
    assert identity.auth_mode == "federated-jwks"
    assert identity.user["firstName"] == "Ada"


def test_identity_accepts_null_tenant():
    """`tenantId: null` is valid per the contract (legacy token mode)."""
    body = json.loads(json.dumps(SESSION_BODY))
    body["identity"]["tenantId"] = None
    assert Identity.from_session_info(body).tenant_id is None


@pytest.mark.parametrize(
    "mutate",
    [
        lambda b: b.pop("identity"),
        lambda b: b["identity"].pop("userId"),
        lambda b: b["identity"].pop("roles"),
        lambda b: b["identity"].pop("authMode"),
        lambda b: b["identity"].update(tenantId=123),
    ],
)
def test_identity_rejects_malformed_session_info(mutate):
    body = json.loads(json.dumps(SESSION_BODY))
    mutate(body)
    with pytest.raises(ValueError):
        Identity.from_session_info(body)


def test_authz_check_payload_uses_bare_policy_keys():
    """The wire payload carries the bare keys from registration/policy.json."""
    payload = AuthzCheck("VaultAsset", "reveal", resource_key="cred-9").to_payload(
        subject="ff-subject-123", tenant="tenant-abc"
    )
    assert payload == {
        "subject": "ff-subject-123",
        "tenant": "tenant-abc",
        "resource": {"type": "VaultAsset", "key": "cred-9"},
        "action": "reveal",
    }


# ── session verification ─────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_get_session_calls_the_contract_endpoint_with_bearer():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["auth"] = request.headers.get("authorization")
        return httpx.Response(200, json=SESSION_BODY)

    identity = await _client(handler).get_session("tok-abc")
    assert seen["url"] == "http://security.test/v1/security/session"
    assert seen["auth"] == "Bearer tok-abc"
    assert identity.user_id == "ff-subject-123"


@pytest.mark.asyncio
async def test_get_session_rejects_empty_token():
    def handler(request):  # pragma: no cover - must never be called
        raise AssertionError("no request should be made without a token")

    with pytest.raises(SecurityError) as exc:
        await _client(handler).get_session("")
    assert exc.value.code == "NO_TOKEN"


@pytest.mark.asyncio
async def test_get_session_401_is_a_denial():
    handler = lambda r: httpx.Response(401, json={"code": "EXPIRED"})
    with pytest.raises(SecurityError) as exc:
        await _client(handler).get_session("tok")
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_get_session_unreachable_service_fails_closed():
    """An unreachable verifier must never be treated as "probably fine"."""

    def handler(request):
        raise httpx.ConnectError("boom")

    with pytest.raises(SecurityError) as exc:
        await _client(handler).get_session("tok")
    assert exc.value.code == "VERIFIER_UNAVAILABLE"
    assert exc.value.status_code == 503


@pytest.mark.asyncio
async def test_get_session_malformed_body_fails_closed():
    handler = lambda r: httpx.Response(200, json={"nope": True})
    with pytest.raises(SecurityError) as exc:
        await _client(handler).get_session("tok")
    assert exc.value.code == "MALFORMED"


@pytest.mark.asyncio
async def test_delete_session_hits_the_contract_endpoint():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["method"] = request.method
        seen["url"] = str(request.url)
        return httpx.Response(204)

    await _client(handler).delete_session("tok")
    assert seen["method"] == "DELETE"
    assert seen["url"] == "http://security.test/v1/security/session"


@pytest.mark.asyncio
async def test_delete_session_swallows_transport_errors():
    """Logout must not 500 because the revoke call flapped."""

    def handler(request):
        raise httpx.ConnectError("boom")

    await _client(handler).delete_session("tok")  # must not raise


# ── authorization ────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_authz_check_allows_on_explicit_allow():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"allow": True})

    allowed = await _client(handler).authz_check(
        subject="s", tenant="t", check=AuthzCheck("VaultAsset", "reveal")
    )
    assert allowed is True
    assert seen["url"] == "http://security.test/v1/security/authz/check"
    assert seen["body"]["resource"] == {"type": "VaultAsset"}
    assert seen["body"]["action"] == "reveal"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "response_factory",
    [
        lambda r: httpx.Response(200, json={"allow": False}),
        lambda r: httpx.Response(200, json={}),  # no decision at all
        lambda r: httpx.Response(200, text="not json"),
        lambda r: httpx.Response(500),
        lambda r: httpx.Response(403),
    ],
    ids=["deny", "no-key", "unparseable", "server-error", "forbidden"],
)
async def test_authz_check_denies_on_anything_but_an_explicit_allow(response_factory):
    allowed = await _client(response_factory).authz_check(
        subject="s", tenant="t", check=AuthzCheck("VaultAsset", "reveal")
    )
    assert allowed is False


@pytest.mark.asyncio
async def test_authz_check_denies_when_service_is_unreachable():
    def handler(request):
        raise httpx.ConnectTimeout("boom")

    allowed = await _client(handler).authz_check(
        subject="s", tenant="t", check=AuthzCheck("VaultAsset", "reveal")
    )
    assert allowed is False


@pytest.mark.asyncio
async def test_bulk_check_is_index_aligned():
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert len(body["checks"]) == 3
        return httpx.Response(
            200,
            json={"decisions": [{"allow": True}, {"allow": False}, {"allow": True}]},
        )

    checks = [
        AuthzCheck("Identity", "read"),
        AuthzCheck("VaultAsset", "reveal"),
        AuthzCheck("Account", "create"),
    ]
    assert await _client(handler).authz_bulk_check("s", "t", checks) == [
        True,
        False,
        True,
    ]


@pytest.mark.asyncio
async def test_bulk_check_length_mismatch_denies_everything():
    """A short decision list must not be silently zipped against the requests.

    Index-aligning a 2-element response onto 3 checks would grant check[0]'s
    decision to the wrong resource. Deny all instead.
    """
    handler = lambda r: httpx.Response(
        200, json={"decisions": [{"allow": True}, {"allow": True}]}
    )
    checks = [
        AuthzCheck("Identity", "read"),
        AuthzCheck("VaultAsset", "reveal"),
        AuthzCheck("Account", "create"),
    ]
    assert await _client(handler).authz_bulk_check("s", "t", checks) == [
        False,
        False,
        False,
    ]


@pytest.mark.asyncio
async def test_bulk_check_unreachable_denies_everything():
    def handler(request):
        raise httpx.ConnectError("boom")

    checks = [AuthzCheck("Identity", "read"), AuthzCheck("Account", "read")]
    assert await _client(handler).authz_bulk_check("s", "t", checks) == [False, False]


@pytest.mark.asyncio
async def test_bulk_check_rejects_more_than_the_contract_maximum():
    """`AuthzBulkCheckRequest.checks` has maxItems: 200."""
    handler = lambda r: httpx.Response(200, json={"decisions": []})
    with pytest.raises(ValueError):
        await _client(handler).authz_bulk_check(
            "s", "t", [AuthzCheck("Identity", "read")] * 201
        )


@pytest.mark.asyncio
async def test_permissions_fails_closed_to_an_empty_set():
    def handler(request):
        raise httpx.ConnectError("boom")

    assert await _client(handler).get_permissions("s", "t") == []


# ── tenant fail-closed ───────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_check_permission_denies_when_identity_has_no_tenant(monkeypatch):
    """Contract: consumers fail closed on tenant-scoped authz when tenantId is null."""
    from app.security import dependencies as deps

    monkeypatch.delenv("FUZEFRONT_DEFAULT_TENANT", raising=False)

    def handler(request):  # pragma: no cover - must never be reached
        raise AssertionError("must not call authz/check without a tenant")

    identity = Identity(
        user_id="s", tenant_id=None, roles=[], auth_mode="federated-jwks"
    )
    assert (
        await deps.check_permission(
            identity, "VaultAsset", "reveal", client=_client(handler)
        )
        is False
    )


@pytest.mark.asyncio
async def test_bulk_check_permissions_denies_all_without_a_tenant(monkeypatch):
    from app.security import dependencies as deps

    monkeypatch.delenv("FUZEFRONT_DEFAULT_TENANT", raising=False)

    def handler(request):  # pragma: no cover
        raise AssertionError("must not call authz/bulk-check without a tenant")

    identity = Identity(
        user_id="s", tenant_id=None, roles=[], auth_mode="federated-jwks"
    )
    decisions = await deps.bulk_check_permissions(
        identity,
        [AuthzCheck("Identity", "read"), AuthzCheck("Account", "read")],
        client=_client(handler),
    )
    assert decisions == [False, False]


# ── the coupling this migration removes ──────────────────────────────────────
def test_no_local_password_helpers_are_exported():
    """`hash_password` / `verify_password` are gone from the public surface.

    They existed only to authenticate users locally. Authentication is
    FuzeFront's now; a public password hasher here is a loaded gun.
    """
    import app.utils.encryption as enc

    assert not hasattr(enc, "hash_password")
    assert not hasattr(enc, "verify_password")


def test_user_model_stores_no_password():
    from app.models.user import User

    columns = {c.name for c in User.__table__.columns}
    assert "hashed_password" not in columns
    assert "fuzefront_user_id" in columns
    # The vault master key is DOMAIN state and stays.
    assert "master_key_hash" in columns


def test_auth_router_exposes_no_login_or_register():
    """There is nothing to log in to here — FuzeFront owns sign-in."""
    from app.routers import auth as auth_router

    paths = {r.path for r in auth_router.router.routes}
    assert "/login" not in paths
    assert "/register" not in paths
    assert "/me" in paths
    assert "/vault/unlock" in paths


def test_auth_router_mints_no_tokens():
    from app.routers import auth as auth_router

    assert not hasattr(auth_router, "create_access_token")
    assert not hasattr(auth_router, "SECRET_KEY")
