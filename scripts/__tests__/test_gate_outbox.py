"""Tests for scripts/gate_outbox.py.

Asserts the gate FAILS on a direct Kafka producer call, and passes
vacuously when no Kafka producers exist. A gate is only worth its
runtime if it is known to fire.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
GATE = os.path.join(REPO_ROOT, "scripts", "gate_outbox.py")


def run_gate(root: str, *flags: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, GATE, root, *flags],
        capture_output=True, text=True, timeout=60,
    )


def make_policy(root: str, mode: str, known: list = None) -> None:
    os.makedirs(os.path.join(root, "governance"), exist_ok=True)
    with open(os.path.join(root, "governance", "outbox-policy.json"), "w") as f:
        json.dump({"mode": mode, "knownUnhandled": known or []}, f)


class TestGateOutboxViolations(unittest.TestCase):
    def test_aiokafka_producer_fails_in_ratchet(self):
        with tempfile.TemporaryDirectory() as root:
            os.makedirs(os.path.join(root, "app"))
            with open(os.path.join(root, "app", "events.py"), "w") as f:
                f.write("from aiokafka import AIOKafkaProducer\n")
                f.write("producer = AIOKafkaProducer(bootstrap_servers='kafka:9092')\n")
            make_policy(root, "ratchet")
            result = run_gate(root)
        self.assertEqual(result.returncode, 1, msg=result.stdout + result.stderr)
        self.assertIn("::error", result.stdout)

    def test_kafka_producer_fails_in_ratchet(self):
        with tempfile.TemporaryDirectory() as root:
            os.makedirs(os.path.join(root, "app"))
            with open(os.path.join(root, "app", "producer.py"), "w") as f:
                f.write("from kafka import KafkaProducer\n")
                f.write("p = KafkaProducer(bootstrap_servers='kafka:9092')\n")
            make_policy(root, "ratchet")
            result = run_gate(root)
        self.assertEqual(result.returncode, 1, msg=result.stdout + result.stderr)

    def test_direct_producer_warns_in_baseline_pending(self):
        with tempfile.TemporaryDirectory() as root:
            os.makedirs(os.path.join(root, "app"))
            with open(os.path.join(root, "app", "events.py"), "w") as f:
                f.write("from aiokafka import AIOKafkaProducer\n")
                f.write("producer = AIOKafkaProducer(bootstrap_servers='kafka:9092')\n")
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
            with open(os.path.join(root, "app", "events.py"), "w") as f:
                f.write("from aiokafka import AIOKafkaProducer\n")
                f.write("producer = AIOKafkaProducer()\n")
            make_policy(root, "ratchet")
            result = run_gate(root, "--report")
        self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)

    def test_relay_path_is_exempt(self):
        """Files in the outbox relay itself are not violations."""
        with tempfile.TemporaryDirectory() as root:
            os.makedirs(os.path.join(root, "outbox"))
            with open(os.path.join(root, "outbox", "relay.py"), "w") as f:
                f.write("from aiokafka import AIOKafkaProducer\n")
                f.write("producer = AIOKafkaProducer()\n")
            make_policy(root, "ratchet")
            result = run_gate(root)
        self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
