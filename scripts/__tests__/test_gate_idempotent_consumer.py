"""Tests for scripts/gate_idempotent_consumer.py.

Asserts the gate FAILS on a raw AIOKafkaConsumer call outside the runtime,
and passes when no raw consumers exist.
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


def make_policy(root: str, mode: str, known: list = None) -> None:
    os.makedirs(os.path.join(root, "governance"), exist_ok=True)
    with open(os.path.join(root, "governance", "idempotent-consumer-policy.json"), "w") as f:
        json.dump({"mode": mode, "knownUnhandled": known or []}, f)


class TestGateIdempotentConsumer(unittest.TestCase):
    def test_aiokafka_consumer_fails_in_ratchet(self):
        with tempfile.TemporaryDirectory() as root:
            os.makedirs(os.path.join(root, "app"))
            with open(os.path.join(root, "app", "worker.py"), "w") as f:
                f.write("from aiokafka import AIOKafkaConsumer\n")
                f.write("consumer = AIOKafkaConsumer('user.created')\n")
            make_policy(root, "ratchet")
            result = run_gate(root)
        self.assertEqual(result.returncode, 1, msg=result.stdout + result.stderr)
        self.assertIn("::error", result.stdout)

    def test_consumer_run_fails_in_ratchet(self):
        with tempfile.TemporaryDirectory() as root:
            os.makedirs(os.path.join(root, "app"))
            with open(os.path.join(root, "app", "worker.py"), "w") as f:
                f.write("await consumer.run()\n")
            make_policy(root, "ratchet")
            result = run_gate(root)
        self.assertEqual(result.returncode, 1, msg=result.stdout + result.stderr)

    def test_raw_consumer_warns_in_baseline_pending(self):
        with tempfile.TemporaryDirectory() as root:
            os.makedirs(os.path.join(root, "app"))
            with open(os.path.join(root, "app", "worker.py"), "w") as f:
                f.write("from aiokafka import AIOKafkaConsumer\n")
                f.write("consumer = AIOKafkaConsumer('topic')\n")
            make_policy(root, "baseline-pending")
            result = run_gate(root)
        self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
        self.assertIn("::warning", result.stdout)

    def test_clean_repo_passes(self):
        with tempfile.TemporaryDirectory() as root:
            os.makedirs(os.path.join(root, "app"))
            with open(os.path.join(root, "app", "main.py"), "w") as f:
                f.write("print('hello world')\n")
            make_policy(root, "ratchet")
            result = run_gate(root)
        self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)

    def test_report_flag_always_exits_zero(self):
        with tempfile.TemporaryDirectory() as root:
            os.makedirs(os.path.join(root, "app"))
            with open(os.path.join(root, "app", "worker.py"), "w") as f:
                f.write("from aiokafka import AIOKafkaConsumer\n")
                f.write("consumer = AIOKafkaConsumer('topic')\n")
            make_policy(root, "ratchet")
            result = run_gate(root, "--report")
        self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)

    def test_runtime_path_is_exempt(self):
        """Files under the event_consumer runtime path are not violations."""
        with tempfile.TemporaryDirectory() as root:
            os.makedirs(os.path.join(root, "event_consumer"))
            with open(os.path.join(root, "event_consumer", "runtime.py"), "w") as f:
                f.write("from aiokafka import AIOKafkaConsumer\n")
                f.write("consumer = AIOKafkaConsumer('topic')\n")
            make_policy(root, "ratchet")
            result = run_gate(root)
        self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
