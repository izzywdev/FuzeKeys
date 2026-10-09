"""Delegated connector requests must use the platform verifier and deny ambiguity."""

from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock

import pytest
from fastapi import HTTPException
from fuzefront_service_auth import TokenVerificationError

from app.security import fuzefront_auth
from app.security.connector_authz import (
    connector_resource_key,
    connector_tenant,
    require_connector_permission,
)


@pytest.mark.asyncio
async def test_delegation_keeps_verified_tenant_in_request_state(monkeypatch):
    from starlette.requests import Request

    machine = fuzefront_auth.Identity(
        subject="svc:caller", scopes=frozenset(), token_kind="fuze-workload"
    )
    delegated = fuzefront_auth.Identity(
        subject="owner",
        scopes=frozenset({"connectors:metadata"}),
        audience="service:fuzekeys",
        actor={"sub": "svc:caller"},
        token_kind="fuze-delegation",
        tenant_id="verified-tenant",
    )
    monkeypatch.setattr(
        fuzefront_auth, "_introspect", Mock(side_effect=[machine, delegated])
    )
    request = Request({"type": "http"})
    result = await fuzefront_auth.delegated_auth("connectors:metadata")(
        request, "Bearer workload", "Bearer delegated"
    )
    assert result.tenant_id == "verified-tenant"
    assert request.state.delegated_identity is delegated
    assert request.state.machine_identity.tenant_id is None


@pytest.mark.asyncio
async def test_personal_delegation_uses_only_the_verified_subject(monkeypatch):
    identity = fuzefront_auth.Identity(
        subject="owner",
        scopes=frozenset({"connectors:metadata"}),
        audience="service:fuzekeys",
        actor={"sub": "svc:caller"},
        token_kind="fuze-delegation",
        tenant_id=None,
    )
    assert connector_tenant(identity) is None
    assert connector_resource_key(None, "owner", "google-gmail")
    # Personal custody is authorized by the verified delegation subject, so it
    # does not call a tenant-scoped platform decision service.
    await require_connector_permission(identity, "google-gmail", "read")


def test_personal_delegation_rejects_an_invalid_subject():
    identity = fuzefront_auth.Identity(
        subject=" ", scopes=frozenset({"connectors:metadata"}),
        audience="service:fuzekeys", actor={"sub": "svc:caller"},
        token_kind="fuze-delegation", tenant_id=None,
    )
    with pytest.raises(HTTPException, match="Verified connector subject required"):
        connector_tenant(identity)


class DelegationVerifierTests(TestCase):
    def setUp(self):
        self.original_verifier = fuzefront_auth._verifier

    def tearDown(self):
        fuzefront_auth._verifier = self.original_verifier

    def test_platform_verifier_identity(self):
        verifier = Mock()
        verifier.verify_machine_token.return_value = SimpleNamespace(
            subject="svc:fuzefront",
            scopes=["connectors:metadata"],
            audience="service:fuzekeys",
            actor={"sub": "svc:caller"},
            token_kind="fuze-delegation",
            tenant_id="verified-tenant",
        )
        fuzefront_auth._verifier = lambda: verifier

        identity = fuzefront_auth._introspect("opaque-token")

        verifier.verify_machine_token.assert_called_once_with("opaque-token")
        self.assertEqual(identity.subject, "svc:fuzefront")
        self.assertEqual(identity.scopes, frozenset({"connectors:metadata"}))
        self.assertEqual(identity.actor, {"sub": "svc:caller"})
        self.assertEqual(identity.tenant_id, "verified-tenant")

    def test_absent_verified_tenant_is_not_inferred(self):
        verifier = Mock()
        verifier.verify_machine_token.return_value = SimpleNamespace(
            subject="owner",
            scopes=["connectors:metadata"],
            audience="service:fuzekeys",
            actor={"sub": "svc:caller", "tenant": "untrusted-actor-field"},
            token_kind="fuze-delegation",
            tenant_id=None,
        )
        fuzefront_auth._verifier = lambda: verifier
        identity = fuzefront_auth._introspect("opaque-token")
        self.assertIsNone(identity.tenant_id)

    def test_platform_verifier_failure_denies(self):
        verifier = Mock()
        verifier.verify_machine_token.side_effect = TokenVerificationError("inactive")
        fuzefront_auth._verifier = lambda: verifier

        with self.assertRaises(HTTPException) as error:
            fuzefront_auth._introspect("inactive-token")

        self.assertEqual(error.exception.status_code, 401)
