"""Workload exchange and explicit allow/deny contract for platform decisions."""

import json

import httpx
import pytest

from app.security import platform_authz


@pytest.mark.asyncio
@pytest.mark.parametrize("allow,expected", [(True, True), (False, False)])
async def test_platform_permission_uses_verified_workload_and_explicit_decision(
    monkeypatch, tmp_path, allow, expected
):
    monkeypatch.setenv("FUZEFRONT_SECURITY_URL", "http://security.internal:3002")
    monkeypatch.setenv("FUZEKEYS_AUTHZ_TENANT", "tenant-1")
    token_file = tmp_path / "token"
    token_file.write_text("projected-sa-token")
    calls = []

    def handler(request):
        calls.append(request)
        if request.url.path.endswith("/tokens/workload"):
            assert json.loads(request.content) == {
                "serviceAccountToken": "projected-sa-token"
            }
            return httpx.Response(200, json={"accessToken": "short-lived-workload"})
        assert request.headers["authorization"] == "Bearer short-lived-workload"
        assert json.loads(request.content) == {
            "subject": "verified-subject",
            "tenant": "tenant-1",
            "resource": {"type": "FuzeKeysAccount", "key": "account-7"},
            "action": "update",
        }
        return httpx.Response(200, json={"allow": allow})

    real_client = httpx.AsyncClient
    monkeypatch.setattr(
        platform_authz.httpx,
        "AsyncClient",
        lambda **kwargs: real_client(transport=httpx.MockTransport(handler), **kwargs),
    )
    assert (
        await platform_authz.check_permission(
            "verified-subject",
            "tenant-1",
            "FuzeKeysAccount",
            "update",
            resource_key="account-7",
            token_path=token_file,
        )
        is expected
    )
    assert len(calls) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "exchange_status,exchange_body,decision_status,decision_body",
    [
        (503, {}, 200, {"allow": True}),
        (200, {"accessToken": ""}, 200, {"allow": True}),
        (200, {"accessToken": "machine"}, 503, {"allow": True}),
        (200, {"accessToken": "machine"}, 200, {"allow": "true"}),
        (200, {"accessToken": "machine"}, 200, {}),
    ],
)
async def test_platform_permission_fails_closed_on_bad_exchange_or_decision(
    monkeypatch,
    tmp_path,
    exchange_status,
    exchange_body,
    decision_status,
    decision_body,
):
    monkeypatch.setenv("FUZEFRONT_SECURITY_URL", "http://security.internal:3002")
    monkeypatch.setenv("FUZEKEYS_AUTHZ_TENANT", "tenant-1")
    token_file = tmp_path / "token"
    token_file.write_text("projected-sa-token")

    def handler(request):
        if request.url.path.endswith("/tokens/workload"):
            return httpx.Response(exchange_status, json=exchange_body)
        return httpx.Response(decision_status, json=decision_body)

    real_client = httpx.AsyncClient
    monkeypatch.setattr(
        platform_authz.httpx,
        "AsyncClient",
        lambda **kwargs: real_client(transport=httpx.MockTransport(handler), **kwargs),
    )
    with pytest.raises(platform_authz.PlatformAuthorizationUnavailable):
        await platform_authz.check_permission(
            "verified-subject",
            "tenant-1",
            "FuzeKeysAccount",
            "update",
            token_path=token_file,
        )


@pytest.mark.asyncio
async def test_platform_permission_rejects_unmapped_tenant_before_network(monkeypatch):
    monkeypatch.setenv("FUZEFRONT_SECURITY_URL", "http://security.internal:3002")
    monkeypatch.setenv("FUZEKEYS_AUTHZ_TENANT", "tenant-1")
    with pytest.raises(platform_authz.PlatformAuthorizationUnavailable):
        await platform_authz.check_permission(
            "subject", "tenant-2", "FuzeKeysAccount", "update"
        )
