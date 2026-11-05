"""Tests for scripts/gate_event_envelope.py.

Asserts the gate FAILS when a registered topic schema is missing
envelope-v2 fields (not merely that it passes on a clean tree).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
GATE = os.path.join(REPO_ROOT, "scripts", "gate_event_envelope.py")


def run_gate(root: str, *flags: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, GATE, root, *flags],
        capture_output=True, text=True, timeout=60,
    )


class SyntheticRepo:
    def __init__(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = self._tmp.name
        subprocess.run(["git", "init", "-q", self.root], check=True)

    def write(self, rel: str, content: str) -> None:
        path = os.path.join(self.root, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(content)

    def policy(self, **fields) -> None:
        gov = os.path.join(self.root, "governance")
        os.makedirs(gov, exist_ok=True)
        with open(os.path.join(gov, "event-envelope-policy.json"), "w") as fh:
            json.dump(fields, fh)

    def commit(self) -> None:
        subprocess.run(["git", "-C", self.root, "add", "-A"], check=True)
        subprocess.run(
            ["git", "-C", self.root, "-c", "user.email=t@t", "-c", "user.name=t",
             "commit", "-qm", "fixture"],
            check=True,
        )

    def __enter__(self) -> "SyntheticRepo":
        return self

    def __exit__(self, *exc) -> None:
        self._tmp.cleanup()


ENVELOPE_SCHEMA = json.dumps({
    "type": "object",
    "properties": {
        "eventId": {"type": "string"},
        "aggregateId": {"type": "string"},
        "aggregateType": {"type": "string"},
        "payload": {"type": "object"},
    },
    "required": ["eventId", "aggregateId", "aggregateType"],
})

MISSING_ENVELOPE_SCHEMA = json.dumps({
    "type": "object",
    "properties": {
        "payload": {"type": "object"},
    },
})


class TestNoRegistryConfigured(unittest.TestCase):
    def test_empty_registry_paths_passes(self):
        with SyntheticRepo() as repo:
            repo.policy(mode="ratchet", registryPaths=[], knownUnhandled=[])
            repo.commit()
            result = run_gate(repo.root)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_missing_policy_passes(self):
        with SyntheticRepo() as repo:
            repo.write("src/app.py", "x = 1\n")
            repo.commit()
            result = run_gate(repo.root)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


class TestEnvelopeEnforcement(unittest.TestCase):
    def test_valid_schema_passes(self):
        with SyntheticRepo() as repo:
            repo.write("events/user.created.json", ENVELOPE_SCHEMA)
            repo.policy(
                mode="ratchet",
                registryPaths=["events/*.json"],
                knownUnhandled=[],
            )
            repo.commit()
            result = run_gate(repo.root)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_missing_envelope_fields_fails_in_ratchet_mode(self):
        """The gate MUST fail when a schema is missing eventId/aggregateId/aggregateType."""
        with SyntheticRepo() as repo:
            repo.write("events/order.placed.json", MISSING_ENVELOPE_SCHEMA)
            repo.policy(
                mode="ratchet",
                registryPaths=["events/*.json"],
                knownUnhandled=[],
            )
            repo.commit()
            result = run_gate(repo.root)
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)

    def test_missing_envelope_in_baseline_pending_exits_0(self):
        with SyntheticRepo() as repo:
            repo.write("events/order.placed.json", MISSING_ENVELOPE_SCHEMA)
            repo.policy(
                mode="baseline-pending",
                registryPaths=["events/*.json"],
                knownUnhandled=[],
            )
            repo.commit()
            result = run_gate(repo.root)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_report_flag_always_exits_0(self):
        with SyntheticRepo() as repo:
            repo.write("events/order.placed.json", MISSING_ENVELOPE_SCHEMA)
            repo.policy(
                mode="ratchet",
                registryPaths=["events/*.json"],
                knownUnhandled=[],
            )
            repo.commit()
            result = run_gate(repo.root, "--report")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_known_violation_passes(self):
        with SyntheticRepo() as repo:
            repo.write("events/order.placed.json", MISSING_ENVELOPE_SCHEMA)
            repo.policy(
                mode="ratchet",
                registryPaths=["events/*.json"],
                knownUnhandled=["events/order.placed.json"],
            )
            repo.commit()
            result = run_gate(repo.root)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
