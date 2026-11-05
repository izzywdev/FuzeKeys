"""Tests for scripts/gate_idempotent_consumer.py.

Each test asserts the gate FAILS on a planted violation or PASSES on a clean tree.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
GATE = os.path.join(REPO_ROOT, "scripts", "gate_idempotent_consumer.py")


def run_gate(root: str, *flags: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, GATE, root, *flags],
        capture_output=True, text=True, timeout=120,
    )


class SyntheticRepo:
    def __init__(self) -> None:
        self._tmp = tempfile.mkdtemp(prefix="gate-consumer-")
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


class TestIdempotentConsumerGate(unittest.TestCase):

    def test_direct_aiokafka_consumer_fails(self):
        """The gate MUST fire on a direct AIOKafkaConsumer instantiation."""
        with SyntheticRepo() as repo:
            repo.write("workers/processor.py", "consumer = AIOKafkaConsumer('topic')\n")
            repo.commit()
            result = run_gate(repo.root)
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("AIOKafkaConsumer", result.stdout)

    def test_consumer_run_fails(self):
        """Direct consumer.run() is forbidden outside the shared runtime."""
        with SyntheticRepo() as repo:
            repo.write("workers/handler.py",
                       "async def start():\n    await consumer.run()\n")
            repo.commit()
            result = run_gate(repo.root)
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("consumer.run", result.stdout)

    def test_runtime_path_is_exempt(self):
        """Files declared in runtimePaths must not be flagged."""
        with SyntheticRepo() as repo:
            repo.write("shared/consumer_runtime.py", "consumer = AIOKafkaConsumer('topic')\n")
            gov = os.path.join(repo.root, "governance")
            os.makedirs(gov, exist_ok=True)
            with open(os.path.join(gov, "idempotent-consumer-policy.json"), "w") as f:
                json.dump({"mode": "fail", "runtimePaths": ["shared/consumer_runtime.py"], "knownUnhandled": []}, f)
            repo.commit()
            result = run_gate(repo.root)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_clean_repo_passes(self):
        """A repo with no raw consumer calls must exit 0."""
        with SyntheticRepo() as repo:
            repo.write("backend/app.py", "def handle(): pass\n")
            repo.commit()
            result = run_gate(repo.root)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_report_mode_always_exits_zero(self):
        """--report must exit 0 even when violations exist."""
        with SyntheticRepo() as repo:
            repo.write("workers/processor.py", "consumer = AIOKafkaConsumer('topic')\n")
            repo.commit()
            result = run_gate(repo.root, "--report")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("AIOKafkaConsumer", result.stdout)

    def test_known_unhandled_suppresses_violation(self):
        """A site listed in knownUnhandled must not block CI."""
        with SyntheticRepo() as repo:
            repo.write("legacy/old_consumer.py", "consumer = KafkaConsumer('topic')\n")
            gov = os.path.join(repo.root, "governance")
            os.makedirs(gov, exist_ok=True)
            with open(os.path.join(gov, "idempotent-consumer-policy.json"), "w") as f:
                json.dump(
                    {"mode": "fail", "runtimePaths": [], "knownUnhandled": ["legacy/old_consumer.py:1"]},
                    f,
                )
            repo.commit()
            result = run_gate(repo.root)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
