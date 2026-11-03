"""Tests for scripts/gate_event_envelope.py.

Asserts the gate FAILS on an event schema that lacks envelope v2 fields,
and passes when schemas are compliant or absent.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
GATE = os.path.join(REPO_ROOT, "scripts", "gate_event_envelope.py")


def run_gate(root: str, *flags: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, GATE, root, *flags],
        capture_output=True, text=True, timeout=60,
    )


def make_policy(root: str, mode: str, known: list = None) -> None:
    os.makedirs(os.path.join(root, "governance"), exist_ok=True)
    with open(os.path.join(root, "governance", "event-envelope-policy.json"), "w") as f:
        json.dump({"mode": mode, "knownUnhandled": known or []}, f)


class TestGateEventEnvelope(unittest.TestCase):
    def test_event_class_missing_envelope_fails_in_ratchet(self):
        """An event class without envelope v2 fields fails."""
        with tempfile.TemporaryDirectory() as root:
            os.makedirs(os.path.join(root, "events"))
            with open(os.path.join(root, "events", "user_events.py"), "w") as f:
                f.write("class UserCreatedEvent:\n")
                f.write("    user_id: str\n")
                f.write("    email: str\n")
            make_policy(root, "ratchet")
            result = run_gate(root)
        self.assertEqual(result.returncode, 1, msg=result.stdout + result.stderr)
        self.assertIn("::error", result.stdout)

    def test_event_class_with_envelope_passes(self):
        """An event class with all v2 envelope fields passes."""
        with tempfile.TemporaryDirectory() as root:
            os.makedirs(os.path.join(root, "events"))
            with open(os.path.join(root, "events", "user_events.py"), "w") as f:
                f.write("class UserCreatedEvent:\n")
                f.write("    event_id: str\n")
                f.write("    aggregate_id: str\n")
                f.write("    aggregate_type: str\n")
                f.write("    occurred_at: str\n")
                f.write("    user_id: str\n")
            make_policy(root, "ratchet")
            result = run_gate(root)
        self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)

    def test_missing_envelope_warns_in_baseline_pending(self):
        """Missing envelope in baseline-pending mode is a warning, not a failure."""
        with tempfile.TemporaryDirectory() as root:
            os.makedirs(os.path.join(root, "events"))
            with open(os.path.join(root, "events", "user_events.py"), "w") as f:
                f.write("class UserCreatedEvent:\n")
                f.write("    user_id: str\n")
            make_policy(root, "baseline-pending")
            result = run_gate(root)
        self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
        self.assertIn("::warning", result.stdout)

    def test_no_event_schemas_passes(self):
        """A repo with no event classes passes vacuously."""
        with tempfile.TemporaryDirectory() as root:
            os.makedirs(os.path.join(root, "app"))
            with open(os.path.join(root, "app", "main.py"), "w") as f:
                f.write("print('hello')\n")
            make_policy(root, "ratchet")
            result = run_gate(root)
        self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)

    def test_report_flag_always_exits_zero(self):
        with tempfile.TemporaryDirectory() as root:
            os.makedirs(os.path.join(root, "events"))
            with open(os.path.join(root, "events", "user_events.py"), "w") as f:
                f.write("class UserCreatedEvent:\n")
                f.write("    user_id: str\n")
            make_policy(root, "ratchet")
            result = run_gate(root, "--report")
        self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)

    def test_camelcase_envelope_fields_pass(self):
        """camelCase envelope fields (eventId, aggregateId, etc.) also satisfy v2."""
        with tempfile.TemporaryDirectory() as root:
            os.makedirs(os.path.join(root, "events"))
            with open(os.path.join(root, "events", "user_events.py"), "w") as f:
                f.write("class UserCreatedEvent:\n")
                f.write("    eventId: str\n")
                f.write("    aggregateId: str\n")
                f.write("    aggregateType: str\n")
                f.write("    occurredAt: str\n")
                f.write("    userId: str\n")
            make_policy(root, "ratchet")
            result = run_gate(root)
        self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
