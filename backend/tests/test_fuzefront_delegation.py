"""Delegated connector requests must use the platform verifier and deny ambiguity."""

from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock

from fastapi import HTTPException
from fuzefront_service_auth import TokenVerificationError

from app.security import fuzefront_auth


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
        )
        fuzefront_auth._verifier = lambda: verifier

        identity = fuzefront_auth._introspect("opaque-token")

        verifier.verify_machine_token.assert_called_once_with("opaque-token")
        self.assertEqual(identity.subject, "svc:fuzefront")
        self.assertEqual(identity.scopes, frozenset({"connectors:metadata"}))
        self.assertEqual(identity.actor, {"sub": "svc:caller"})

    def test_platform_verifier_failure_denies(self):
        verifier = Mock()
        verifier.verify_machine_token.side_effect = TokenVerificationError("inactive")
        fuzefront_auth._verifier = lambda: verifier

        with self.assertRaises(HTTPException) as error:
            fuzefront_auth._introspect("inactive-token")

        self.assertEqual(error.exception.status_code, 401)
