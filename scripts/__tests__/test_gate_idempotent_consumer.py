"""Tests for scripts/gate_idempotent_consumer.py.

Asserts the gate FAILS when raw Kafka consumer construction is found
outside the declared runtime paths (not merely that it passes on a clean tree).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
GATE = os.path.join(REPO_ROOT, "scripts", "gate_idempotent_consumer.py")


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
        with open(os.path.join(gov, "idempotent-consumer-policy.json"), "w") as fh:
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


CLEAN_CODE = "from app.runtime import consume\n\nasync def handler(msg):\n    await consume(msg)\n"
RAW_CONSUMER = "from aiokafka import AIOKafkaConsumer\n\nconsumer = AIOKafkaConsumer('topic', bootstrap_servers='localhost')\n"


class TestNoKafkaCode(unittest.TestCase):
    def test_clean_repo_passes(self):
        with SyntheticRepo() as repo:
            repo.write("backend/app/worker.py", CLEAN_CODE)
            repo.policy(mode="ratchet", runtimePaths=[], knownUnhandled=[])
            repo.commit()
            result = run_gate(repo.root)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_missing_policy_passes(self):
        with SyntheticRepo() as repo:
            repo.write("backend/app/worker.py", CLEAN_CODE)
            repo.commit()
            result = run_gate(repo.root)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


class TestRawConsumerDetection(unittest.TestCase):
    def test_aiokafkaconsumer_outside_runtime_fails(self):
        """The gate MUST fail when AIOKafkaConsumer is used outside runtimePaths."""
        with SyntheticRepo() as repo:
            repo.write("backend/app/worker.py", RAW_CONSUMER)
            repo.policy(mode="ratchet", runtimePaths=[], knownUnhandled=[])
            repo.commit()
            result = run_gate(repo.root)
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)

    def test_consumer_in_baseline_pending_exits_0(self):
        with SyntheticRepo() as repo:
            repo.write("backend/app/worker.py", RAW_CONSUMER)
            repo.policy(mode="baseline-pending", runtimePaths=[], knownUnhandled=[])
            repo.commit()
            result = run_gate(repo.root)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_consumer_inside_runtime_path_passes(self):
        with SyntheticRepo() as repo:
            repo.write("backend/app/runtime/consumer.py", RAW_CONSUMER)
            repo.policy(
                mode="ratchet",
                runtimePaths=["backend/app/runtime"],
                knownUnhandled=[],
            )
            repo.commit()
            result = run_gate(repo.root)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_known_violation_passes(self):
        with SyntheticRepo() as repo:
            repo.write("backend/app/worker.py", RAW_CONSUMER)
            repo.policy(
                mode="ratchet",
                runtimePaths=[],
                knownUnhandled=["backend/app/worker.py"],
            )
            repo.commit()
            result = run_gate(repo.root)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_report_flag_always_exits_0(self):
        with SyntheticRepo() as repo:
            repo.write("backend/app/worker.py", RAW_CONSUMER)
            repo.policy(mode="ratchet", runtimePaths=[], knownUnhandled=[])
            repo.commit()
            result = run_gate(repo.root, "--report")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
