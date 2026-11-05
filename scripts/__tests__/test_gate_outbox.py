"""Tests for scripts/gate_outbox.py.

Each test asserts the gate FAILS on a planted violation or PASSES on a clean tree.
A gate tested only on clean trees is indistinguishable from one that runs nothing.
"""
from __future__ import annotations

import os
import subprocess
import sys
import shutil
import tempfile
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
GATE = os.path.join(REPO_ROOT, "scripts", "gate_outbox.py")


def run_gate(root: str, *flags: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, GATE, root, *flags],
        capture_output=True, text=True, timeout=120,
    )


class SyntheticRepo:
    def __init__(self) -> None:
        self._tmp = tempfile.mkdtemp(prefix="gate-outbox-")
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


class TestOutboxGate(unittest.TestCase):

    def test_direct_aiokafka_producer_fails(self):
        """The gate MUST fire on a direct AIOKafkaProducer instantiation."""
        with SyntheticRepo() as repo:
            repo.write("backend/notify.py", "producer = AIOKafkaProducer()\n")
            repo.commit()
            result = run_gate(repo.root)
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("AIOKafkaProducer", result.stdout)

    def test_direct_producer_send_fails(self):
        """Direct producer.send() calls are forbidden outside the outbox relay."""
        with SyntheticRepo() as repo:
            repo.write("services/email.py",
                       "async def send():\n    await producer.send('topic', b'data')\n")
            repo.commit()
            result = run_gate(repo.root)
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("producer.send", result.stdout)

    def test_outbox_relay_path_is_exempt(self):
        """The outbox relay itself legitimately instantiates producers; it must not be flagged."""
        with SyntheticRepo() as repo:
            repo.write("backend/outbox/relay.py", "producer = AIOKafkaProducer()\n")
            repo.commit()
            result = run_gate(repo.root)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_clean_repo_passes(self):
        """A repo with no Kafka producer calls must exit 0."""
        with SyntheticRepo() as repo:
            repo.write("backend/app.py", "def hello(): return 'world'\n")
            repo.commit()
            result = run_gate(repo.root)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_report_mode_always_exits_zero(self):
        """--report must exit 0 even when violations exist."""
        with SyntheticRepo() as repo:
            repo.write("backend/notify.py", "producer = AIOKafkaProducer()\n")
            repo.commit()
            result = run_gate(repo.root, "--report")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("AIOKafkaProducer", result.stdout)

    def test_known_unhandled_suppresses_violation(self):
        """A site listed in knownUnhandled must not block CI."""
        import json
        with SyntheticRepo() as repo:
            repo.write("backend/legacy.py", "producer = KafkaProducer()\n")
            gov = os.path.join(repo.root, "governance")
            os.makedirs(gov, exist_ok=True)
            with open(os.path.join(gov, "outbox-policy.json"), "w") as f:
                json.dump({"mode": "fail", "knownUnhandled": ["backend/legacy.py:1"]}, f)
            repo.commit()
            result = run_gate(repo.root)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
