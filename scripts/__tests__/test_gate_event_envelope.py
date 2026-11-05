"""Tests for scripts/gate_event_envelope.py.

Each test asserts the gate FAILS on a planted violation or PASSES on a clean tree.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
GATE = os.path.join(REPO_ROOT, "scripts", "gate_event_envelope.py")


def run_gate(root: str, *flags: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, GATE, root, *flags],
        capture_output=True, text=True, timeout=120,
    )


class SyntheticRepo:
    def __init__(self) -> None:
        self._tmp = tempfile.mkdtemp(prefix="gate-envelope-")
        subprocess.run(["git", "init", "-q", self._tmp], check=True)
        subprocess.run(
            ["git", "-C", self._tmp, "-c", "user.email=t@t", "-c", "user.name=t",
             "commit", "-q", "--allow-empty", "-m", "init"],
            check=True,
        )

    @property
    def root(self) -> str:
        return self._tmp

    def write(self, rel: str, content: str) -> None:
        path = os.path.join(self._tmp, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)

    def commit(self) -> None:
        subprocess.run(["git", "-C", self._tmp, "add", "-A"], check=True)
        subprocess.run(
            ["git", "-C", self._tmp, "-c", "user.email=t@t", "-c", "user.name=t",
             "commit", "-q", "-m", "fixture"],
            check=True,
        )

    def __enter__(self) -> "SyntheticRepo":
        return self

    def __exit__(self, *exc) -> None:
        shutil.rmtree(self._tmp, ignore_errors=True)


# A minimal valid envelope v2 event schema (Python).
VALID_EVENT_PY = """\
from dataclasses import dataclass

@dataclass
class UserCreatedEvent:
    event_id: str
    aggregate_id: str
    aggregate_type: str
    occurred_at: str
    user_email: str
"""

# A schema missing all envelope fields.
INVALID_EVENT_PY = """\
from dataclasses import dataclass

@dataclass
class UserCreatedEvent:
    user_email: str
"""

# A minimal valid envelope v2 event schema (TypeScript).
VALID_EVENT_TS = """\
export interface UserCreatedEvent {
  eventId: string;
  aggregateId: string;
  aggregateType: string;
  occurredAt: string;
  userEmail: string;
}
"""

# A TypeScript schema missing envelope fields.
INVALID_EVENT_TS = """\
export interface UserCreatedEvent {
  userEmail: string;
}
"""


class TestEventEnvelopeGate(unittest.TestCase):

    def test_python_event_missing_envelope_fields_fails(self):
        """The gate MUST fire when an event class lacks the required envelope fields."""
        with SyntheticRepo() as repo:
            repo.write("backend/events/user_events.py", INVALID_EVENT_PY)
            repo.commit()
            result = run_gate(repo.root)
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("UserCreatedEvent", result.stdout)

    def test_python_event_with_all_envelope_fields_passes(self):
        """A valid envelope v2 event schema must not trigger the gate."""
        with SyntheticRepo() as repo:
            repo.write("backend/events/user_events.py", VALID_EVENT_PY)
            repo.commit()
            result = run_gate(repo.root)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_typescript_event_missing_envelope_fields_fails(self):
        """The gate must fire for TypeScript schemas too."""
        with SyntheticRepo() as repo:
            repo.write("frontend/src/events/user_events.ts", INVALID_EVENT_TS)
            repo.commit()
            result = run_gate(repo.root)
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)

    def test_repo_with_no_event_schemas_passes_vacuously(self):
        """A repo with no event-schema files must exit 0 (vacuous pass)."""
        with SyntheticRepo() as repo:
            repo.write("backend/app.py", "def hello(): return 'world'\n")
            repo.commit()
            result = run_gate(repo.root)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_report_mode_always_exits_zero(self):
        """--report must exit 0 even when violations exist."""
        with SyntheticRepo() as repo:
            repo.write("backend/events/user_events.py", INVALID_EVENT_PY)
            repo.commit()
            result = run_gate(repo.root, "--report")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_test_files_are_skipped(self):
        """Event classes in test directories must not trigger the gate."""
        with SyntheticRepo() as repo:
            repo.write("tests/test_events.py", INVALID_EVENT_PY)
            repo.commit()
            result = run_gate(repo.root)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
