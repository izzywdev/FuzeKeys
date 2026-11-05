"""Self-tests for gate_outbox.

Each case asserts the gate FAILS on direct Kafka producer calls outside the outbox
relay, and PASSES when such calls are absent or in the declared allowed paths.
Violation cases run first — a gate proven only on a clean tree is not proven.
"""
import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import gate_outbox as gate


class Base(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="gate-outbox-")
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)

    def w(self, rel: str, text: str) -> str:
        path = os.path.join(self.root, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        return path

    def policy(self, mode="ratchet", allowed=None, known=None):
        data = {
            "mode": mode,
            "allowedProducerPaths": allowed or [],
            "knownUnhandled": known or [],
        }
        self.w("governance/outbox-policy.json", json.dumps(data))


class ViolationTests(Base):
    """Gate MUST fail on these inputs."""

    def test_aiokafkaproducer_outside_relay_fails(self):
        self.w("backend/app/notify.py",
               "from aiokafka import AIOKafkaProducer\n"
               "async def send():\n"
               "    p = AIOKafkaProducer(bootstrap_servers='kafka:9092')\n")
        self.policy()
        self.assertEqual(gate.main([self.root]), 1)

    def test_kafkaproducer_outside_relay_fails(self):
        self.w("backend/app/events.py",
               "from kafka import KafkaProducer\n"
               "p = KafkaProducer()\n")
        self.policy()
        self.assertEqual(gate.main([self.root]), 1)

    def test_producer_send_outside_relay_fails(self):
        self.w("backend/app/notify.py",
               "producer.send('topic', value=data)\n")
        self.policy()
        self.assertEqual(gate.main([self.root]), 1)

    def test_producer_produce_outside_relay_fails(self):
        self.w("backend/app/notify.py",
               "producer.produce('topic', value=data)\n")
        self.policy()
        self.assertEqual(gate.main([self.root]), 1)

    def test_typescript_kafka_producer_fails(self):
        self.w("frontend/src/events.ts",
               "const producer = kafka.producer();\n"
               "producer.send({ topic: 'events', messages: [] });\n")
        self.policy()
        self.assertEqual(gate.main([self.root]), 1)


class CleanTests(Base):
    """Gate MUST pass on these inputs."""

    def test_clean_codebase_passes(self):
        self.w("backend/app/main.py",
               "from fastapi import FastAPI\napp = FastAPI()\n")
        self.policy()
        self.assertEqual(gate.main([self.root]), 0)

    def test_allowed_path_passes(self):
        self.w("backend/outbox/relay.py",
               "from aiokafka import AIOKafkaProducer\n"
               "p = AIOKafkaProducer()\n")
        self.policy(allowed=["backend/outbox"])
        self.assertEqual(gate.main([self.root]), 0)

    def test_known_unhandled_passes(self):
        self.w("backend/app/notify.py",
               "from aiokafka import AIOKafkaProducer\n"
               "p = AIOKafkaProducer()\n")
        self.policy(known=["backend/app/notify.py:2"])
        self.assertEqual(gate.main([self.root]), 0)

    def test_baseline_pending_always_passes(self):
        self.w("backend/app/notify.py",
               "from aiokafka import AIOKafkaProducer\n"
               "p = AIOKafkaProducer()\n")
        self.policy(mode="baseline-pending")
        self.assertEqual(gate.main([self.root]), 0)

    def test_report_mode_always_passes(self):
        self.w("backend/app/notify.py",
               "from aiokafka import AIOKafkaProducer\n"
               "p = AIOKafkaProducer()\n")
        self.policy(mode="ratchet")
        self.assertEqual(gate.main([self.root, "--report"]), 0)


if __name__ == "__main__":
    unittest.main()
