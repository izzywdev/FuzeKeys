"""Tests for scripts/event_gate_lib.py.

Asserts the ratchet logic FAILS on violations (not merely passes on a clean
tree) and that the library's helper functions behave correctly.
"""
from __future__ import annotations

import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[1] / "event_gate_lib.py"
_spec = importlib.util.spec_from_file_location("event_gate_lib", MODULE_PATH)
lib = importlib.util.module_from_spec(_spec)
assert _spec and _spec.loader
_spec.loader.exec_module(lib)


class TestLoadPolicy(unittest.TestCase):
    def test_missing_file_returns_safe_defaults(self):
        with tempfile.TemporaryDirectory() as tmp:
            policy = lib.load_policy(tmp, "nonexistent")
        self.assertEqual(policy["mode"], "baseline-pending")
        self.assertEqual(policy["knownUnhandled"], [])

    def test_loads_existing_policy(self):
        with tempfile.TemporaryDirectory() as tmp:
            gov = os.path.join(tmp, "governance")
            os.makedirs(gov)
            data = {"mode": "ratchet", "knownUnhandled": ["src/worker.py"]}
            with open(os.path.join(gov, "mygate-policy.json"), "w") as fh:
                json.dump(data, fh)
            policy = lib.load_policy(tmp, "mygate")
        self.assertEqual(policy["mode"], "ratchet")
        self.assertEqual(policy["knownUnhandled"], ["src/worker.py"])


class TestRunRatchet(unittest.TestCase):
    """run_ratchet must FAIL on new violations in ratchet mode."""

    _FINDING = [("src/app.py", 10, "AIOKafkaProducer()")]

    def test_baseline_pending_always_exits_0_even_with_findings(self):
        policy = {"mode": "baseline-pending", "knownUnhandled": []}
        rc = lib.run_ratchet(self._FINDING, policy, "test-gate")
        self.assertEqual(rc, 0)

    def test_ratchet_new_violation_fails(self):
        policy = {"mode": "ratchet", "knownUnhandled": []}
        rc = lib.run_ratchet(self._FINDING, policy, "test-gate")
        self.assertEqual(rc, 1)

    def test_ratchet_known_violation_passes(self):
        policy = {"mode": "ratchet", "knownUnhandled": ["src/app.py"]}
        rc = lib.run_ratchet(self._FINDING, policy, "test-gate")
        self.assertEqual(rc, 0)

    def test_ratchet_stale_known_entry_fails(self):
        """An entry in knownUnhandled with no matching finding must be removed."""
        policy = {"mode": "ratchet", "knownUnhandled": ["src/gone.py"]}
        rc = lib.run_ratchet([], policy, "test-gate")
        self.assertEqual(rc, 1)

    def test_ratchet_no_findings_no_known_passes(self):
        policy = {"mode": "ratchet", "knownUnhandled": []}
        rc = lib.run_ratchet([], policy, "test-gate")
        self.assertEqual(rc, 0)

    def test_ratchet_new_and_known_mixed_fails(self):
        """When both new and known violations are present the gate still fails."""
        policy = {"mode": "ratchet", "knownUnhandled": ["src/app.py"]}
        findings = [
            ("src/app.py", 10, "AIOKafkaProducer()"),  # known
            ("src/worker.py", 5, "AIOKafkaProducer()"),  # new
        ]
        rc = lib.run_ratchet(findings, policy, "test-gate")
        self.assertEqual(rc, 1)


class TestIsExcluded(unittest.TestCase):
    def test_exact_path_excluded(self):
        self.assertTrue(lib._is_excluded("backend/app/outbox.py", ["backend/app/outbox.py"]))

    def test_prefix_excluded(self):
        self.assertTrue(lib._is_excluded("backend/app/outbox/relay.py", ["backend/app/outbox"]))

    def test_unrelated_path_not_excluded(self):
        self.assertFalse(lib._is_excluded("backend/app/service.py", ["backend/app/outbox"]))


if __name__ == "__main__":
    unittest.main()
