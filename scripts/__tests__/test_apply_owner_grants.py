import importlib.util
import sys
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import AsyncMock

scripts = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(scripts))
spec = importlib.util.spec_from_file_location(
    "apply_owner", scripts / "apply_owner_grants.py"
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
from owner_grant_inventory import build_inventory


def inventory():
    return build_inventory(
        [
            dict(
                resource_type="Identity",
                resource_key="identity:3",
                user_id=7,
                subject="user:one",
                tenant="tenant:one",
                verified_at="date",
            )
        ]
    )


class Response:
    def __init__(self, body, bad=False):
        self.body, self.bad = body, bad

    def raise_for_status(self):
        if self.bad:
            raise RuntimeError("provider error")

    def json(self):
        return self.body


class InventoryApplyTests(unittest.TestCase):
    def test_review_checksum_exact_namespace_and_single_tenant(self):
        report = inventory()
        self.assertEqual(
            module.validate_inventory(report, report["checksum_sha256"], "tenant:one"),
            report["grants"],
        )
        for bad in ["different", "", None]:
            with self.assertRaises(module.ProvisioningRejected):
                module.validate_inventory(report, bad, "tenant:one")
        for mutate in [
            lambda r: r.update(ready=1),
            lambda r: r.update(rejected=[{"reason": "missing"}]),
            lambda r: r["grants"][0].update(tenant="other"),
            lambda r: r["grants"][0].update(role="admin"),
            lambda r: r["grants"][0].update(resource_type="Organization"),
            lambda r: r["grants"][0].update(resource_key="identity:03"),
            lambda r: r["grants"][0].update(resource_key="identity:0"),
            lambda r: r["grants"][0].update(permission="all"),
            lambda r: r.update(resource_count=True),
        ]:
            bad = deepcopy(report)
            mutate(bad)
            with self.assertRaises(module.ProvisioningRejected):
                module.validate_inventory(bad, report["checksum_sha256"], "tenant:one")

    def test_token_destination_has_no_redirect_credentials_or_path(self):
        self.assertEqual(
            module.security_origin("https://security.example/"),
            "https://security.example",
        )
        for url in [
            "http://security.example",
            "https://user:pass@security.example",
            "https://security.example/api",
            "https://security.example?token=x",
            "https://security.example#x",
        ]:
            with self.assertRaises(module.ProvisioningRejected):
                module.security_origin(url)


class ApplyFlowTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.grants = inventory()["grants"]
        self.client = AsyncMock()
        self.client.get.return_value = Response(
            {"subject": "user:one", "tenant": "tenant:one", "active": True}
        )
        self.events = []
        self.snapshot = AsyncMock()

    async def apply(self, apply=True):
        return await module.provision(
            self.client,
            self.grants,
            apply=apply,
            verify_snapshot=self.snapshot,
            journal=self.events.append,
        )

    async def test_preflight_never_grants(self):
        self.assertEqual(await self.apply(False), 0)
        self.client.post.assert_not_awaited()
        self.snapshot.assert_awaited_once()
        self.assertEqual(self.events, [])

    async def test_stale_or_malformed_membership_never_mutates(self):
        for proof in [
            None,
            {"active": True},
            {"subject": "user:one", "tenant": "tenant:one", "active": 1},
            {"subject": "user:one", "tenant": "other", "active": True},
        ]:
            self.client.get.return_value = Response(proof)
            with self.assertRaises(module.ProvisioningRejected):
                await self.apply()
            self.client.post.assert_not_awaited()

    async def test_all_subject_memberships_checked_before_first_mutation(self):
        self.grants.append(
            {**self.grants[0], "subject": "user:two", "resource_key": "identity:4"}
        )
        self.client.get.side_effect = [
            Response({"subject": "user:one", "tenant": "tenant:one", "active": True}),
            Response({}, bad=True),
        ]
        with self.assertRaises(RuntimeError):
            await self.apply()
        self.client.post.assert_not_awaited()

    async def test_sql_drift_aborts_before_grant(self):
        self.snapshot.side_effect = module.ProvisioningRejected("changed")
        with self.assertRaises(module.ProvisioningRejected):
            await self.apply()
        self.client.post.assert_not_awaited()

    async def test_apply_exact_tuple_then_positive_and_negative_canaries(self):
        self.client.post.side_effect = [
            Response(module.tuple_payload(self.grants[0])),
            Response({"allow": True}),
            Response({"allow": True}),
            Response({"allow": True}),
            Response({"allow": True}),
            Response({"allow": False}),
        ]
        self.assertEqual(await self.apply(), 1)
        first = self.client.post.await_args_list[0]
        self.assertEqual(first.args, ("/api/v1/security/authz/grants",))
        self.assertEqual(first.kwargs["json"], module.tuple_payload(self.grants[0]))
        self.assertEqual(
            [e["event"] for e in self.events],
            ["grant-requested", "grant-acknowledged", "canary-verified"],
        )
        self.assertEqual(self.client.get.await_count, 2)
        self.assertEqual(self.snapshot.await_count, 2)
        self.assertEqual(
            [
                call.kwargs["json"]["action"]
                for call in self.client.post.await_args_list[1:]
            ],
            ["read", "update", "delete", "use", "update"],
        )

    async def test_indeterminate_write_has_intent_and_never_revoke(self):
        self.client.post.side_effect = RuntimeError("lost response")
        with self.assertRaises(RuntimeError):
            await self.apply()
        self.assertEqual([e["event"] for e in self.events], ["grant-requested"])
        self.client.delete.assert_not_awaited()

    async def test_canary_failure_records_grant_without_claiming_success(self):
        self.client.post.side_effect = [
            Response(module.tuple_payload(self.grants[0])),
            Response({"allow": 1}),
        ]
        with self.assertRaises(module.ProvisioningRejected):
            await self.apply()
        self.assertEqual(
            [e["event"] for e in self.events], ["grant-requested", "grant-acknowledged"]
        )
        self.client.delete.assert_not_awaited()

    async def test_missing_identity_use_stops_before_success_journal(self):
        self.client.post.side_effect = [
            Response(module.tuple_payload(self.grants[0])),
            Response({"allow": True}),
            Response({"allow": True}),
            Response({"allow": True}),
            Response({"allow": False}),
        ]
        with self.assertRaises(module.ProvisioningRejected):
            await self.apply()
        self.assertEqual(
            [e["event"] for e in self.events], ["grant-requested", "grant-acknowledged"]
        )
        self.client.delete.assert_not_awaited()
