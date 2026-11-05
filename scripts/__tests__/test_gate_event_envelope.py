"""Self-tests for gate_event_envelope.

Each case asserts the gate FAILS on a schema missing v2 envelope fields
(eventId, aggregateId, aggregateType, timestamp), and PASSES on compliant schemas.
A gate proven only on a clean tree is not proven — these run violations first.
"""
import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import gate_event_envelope as gate


class Base(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="gate-ee-")
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)

    def w(self, rel: str, text: str) -> str:
        path = os.path.join(self.root, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        return path

    def policy(self, mode="ratchet", registry_paths=None, known=None):
        data = {
            "mode": mode,
            "registryPaths": registry_paths or [],
            "knownUnhandled": known or [],
        }
        self.w("governance/event-envelope-policy.json", json.dumps(data))

    def schema(self, rel: str, properties: dict):
        self.w(rel, json.dumps({"type": "object", "properties": properties}))


class ViolationTests(Base):
    """Gate MUST fail on these inputs."""

    def test_missing_all_v2_fields_fails(self):
        self.schema("events/legacy.json", {
            "id": {"type": "string"},
            "data": {"type": "object"},
        })
        self.policy(mode="ratchet", registry_paths=["events"])
        self.assertEqual(gate.main([self.root]), 1)

    def test_partial_v2_fields_fails(self):
        """Only eventId present — gate must still fail."""
        self.schema("events/partial.json", {
            "eventId": {"type": "string"},
            "payload": {"type": "object"},
        })
        self.policy(mode="ratchet", registry_paths=["events"])
        self.assertEqual(gate.main([self.root]), 1)

    def test_stale_known_unhandled_fails(self):
        """A knownUnhandled entry with no matching finding is stale and must fail."""
        self.schema("events/compliant.json", {
            "eventId": {"type": "string"},
            "aggregateId": {"type": "string"},
            "aggregateType": {"type": "string"},
            "timestamp": {"type": "string"},
        })
        self.policy(
            mode="ratchet",
            registry_paths=["events"],
            known=["events/compliant.json:1"],  # was a violation, now fixed
        )
        self.assertEqual(gate.main([self.root]), 1)


class CleanTests(Base):
    """Gate MUST pass on these inputs."""

    def test_no_registry_paths_passes(self):
        """No registryPaths declared — nothing to check."""
        self.policy(mode="ratchet", registry_paths=[])
        self.assertEqual(gate.main([self.root]), 0)

    def test_v2_compliant_schema_passes(self):
        self.schema("events/user-created.json", {
            "eventId": {"type": "string"},
            "aggregateId": {"type": "string"},
            "aggregateType": {"type": "string"},
            "timestamp": {"type": "string"},
            "payload": {"type": "object"},
        })
        self.policy(mode="ratchet", registry_paths=["events"])
        self.assertEqual(gate.main([self.root]), 0)

    def test_violation_known_unhandled_passes(self):
        self.schema("events/legacy.json", {"id": {"type": "string"}})
        self.policy(
            mode="ratchet",
            registry_paths=["events"],
            known=["events/legacy.json:1"],
        )
        self.assertEqual(gate.main([self.root]), 0)

    def test_baseline_pending_always_passes(self):
        self.schema("events/legacy.json", {"id": {"type": "string"}})
        self.policy(mode="baseline-pending", registry_paths=["events"])
        self.assertEqual(gate.main([self.root]), 0)

    def test_report_mode_always_passes(self):
        self.schema("events/legacy.json", {"id": {"type": "string"}})
        self.policy(mode="ratchet", registry_paths=["events"])
        self.assertEqual(gate.main([self.root, "--report"]), 0)


if __name__ == "__main__":
    unittest.main()
