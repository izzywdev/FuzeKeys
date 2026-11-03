"""Tests for scripts/event_gate_lib.py.

Asserts the library's policy loading, ratchet evaluation, and finding
accumulation work correctly, including that ratchet mode FAILS on new
violations and stale known entries.
"""
from __future__ import annotations

import json
import os
import tempfile
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import sys
sys.path.insert(0, os.path.join(REPO_ROOT, "scripts"))

from event_gate_lib import GateResult, load_policy


class TestLoadPolicy(unittest.TestCase):
    def test_missing_file_returns_default(self):
        with tempfile.TemporaryDirectory() as root:
            policy = load_policy(root, "gate-outbox")
        self.assertEqual(policy["mode"], "baseline-pending")
        self.assertEqual(policy["knownUnhandled"], [])

    def test_loads_valid_policy(self):
        with tempfile.TemporaryDirectory() as root:
            os.makedirs(os.path.join(root, "governance"))
            with open(os.path.join(root, "governance", "outbox-policy.json"), "w") as f:
                json.dump({"mode": "ratchet", "knownUnhandled": ["a.py:1 — x"]}, f)
            policy = load_policy(root, "gate-outbox")
        self.assertEqual(policy["mode"], "ratchet")
        self.assertEqual(policy["knownUnhandled"], ["a.py:1 — x"])

    def test_unknown_mode_defaults_to_baseline_pending(self):
        with tempfile.TemporaryDirectory() as root:
            os.makedirs(os.path.join(root, "governance"))
            with open(os.path.join(root, "governance", "outbox-policy.json"), "w") as f:
                json.dump({"mode": "unknown-mode", "knownUnhandled": []}, f)
            policy = load_policy(root, "gate-outbox")
        self.assertEqual(policy["mode"], "baseline-pending")

    def test_malformed_json_returns_default(self):
        with tempfile.TemporaryDirectory() as root:
            os.makedirs(os.path.join(root, "governance"))
            with open(os.path.join(root, "governance", "outbox-policy.json"), "w") as f:
                f.write("not json {{{")
            policy = load_policy(root, "gate-outbox")
        self.assertEqual(policy["mode"], "baseline-pending")


class TestGateResultBaselinePending(unittest.TestCase):
    def _make(self, findings: list[str]) -> GateResult:
        policy = {"mode": "baseline-pending", "knownUnhandled": []}
        g = GateResult("gate-test", policy)
        for f in findings:
            g.add(f)
        return g

    def test_no_findings_passes(self):
        g = self._make([])
        self.assertEqual(g.evaluate(), 0)

    def test_findings_exit_zero_in_baseline_pending(self):
        g = self._make(["a.py:1 — violation"])
        self.assertEqual(g.evaluate(), 0)


class TestGateResultRatchet(unittest.TestCase):
    def _make(self, findings: list[str], known: list[str]) -> GateResult:
        policy = {"mode": "ratchet", "knownUnhandled": known}
        g = GateResult("gate-test", policy)
        for f in findings:
            g.add(f)
        return g

    def test_new_violation_fails(self):
        g = self._make(["a.py:1 — new violation"], [])
        self.assertEqual(g.evaluate(), 1)

    def test_known_violation_still_present_warns_not_fails(self):
        g = self._make(["a.py:1 — known"], ["a.py:1 — known"])
        self.assertEqual(g.evaluate(), 0)

    def test_stale_known_entry_fails(self):
        # Known entry listed but violation no longer exists → must remove it
        g = self._make([], ["a.py:1 — stale"])
        self.assertEqual(g.evaluate(), 1)

    def test_clean_ratchet_passes(self):
        g = self._make([], [])
        self.assertEqual(g.evaluate(), 0)

    def test_report_only_always_zero(self):
        g = self._make(["a.py:1 — new violation"], [])
        self.assertEqual(g.evaluate(report_only=True), 0)
