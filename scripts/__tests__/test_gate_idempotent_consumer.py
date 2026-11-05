"""Self-tests for gate_idempotent_consumer.

Each case asserts the gate FAILS on raw Kafka consumer instantiation outside
the declared runtime paths, and PASSES when such patterns are absent or allowed.
Violation cases run first — a gate proven only on a clean tree is not proven.
"""
import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import gate_idempotent_consumer as gate


class Base(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="gate-ic-")
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)

    def w(self, rel: str, text: str) -> str:
        path = os.path.join(self.root, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        return path

    def policy(self, mode="ratchet", runtime_paths=None, known=None):
        data = {
            "mode": mode,
            "runtimePackagePaths": runtime_paths or [],
            "knownUnhandled": known or [],
        }
        self.w("governance/idempotent-consumer-policy.json", json.dumps(data))


class ViolationTests(Base):
    """Gate MUST fail on these inputs."""

    def test_aiokafkaconsumer_outside_runtime_fails(self):
        self.w("backend/app/worker.py",
               "from aiokafka import AIOKafkaConsumer\n"
               "async def run():\n"
               "    c = AIOKafkaConsumer('topic')\n")
        self.policy()
        self.assertEqual(gate.main([self.root]), 1)

    def test_kafkaconsumer_outside_runtime_fails(self):
        self.w("backend/app/worker.py",
               "from kafka import KafkaConsumer\n"
               "c = KafkaConsumer('topic')\n")
        self.policy()
        self.assertEqual(gate.main([self.root]), 1)

    def test_typescript_kafka_consumer_fails(self):
        self.w("src/workers/consumer.ts",
               "const consumer = kafka.consumer({ groupId: 'my-group' });\n"
               "await consumer.run({\n"
               "  eachMessage: async ({ message }) => {},\n"
               "});\n")
        self.policy()
        self.assertEqual(gate.main([self.root]), 1)


class CleanTests(Base):
    """Gate MUST pass on these inputs."""

    def test_clean_codebase_passes(self):
        self.w("backend/app/main.py",
               "from fastapi import FastAPI\napp = FastAPI()\n")
        self.policy()
        self.assertEqual(gate.main([self.root]), 0)

    def test_consumer_run_without_kafka_import_passes(self):
        """consumer.run( without a kafka import must not trigger the gate."""
        self.w("backend/app/worker.py",
               "class Worker:\n"
               "    def start(self):\n"
               "        consumer.run()\n")
        self.policy()
        self.assertEqual(gate.main([self.root]), 0)

    def test_allowed_runtime_path_passes(self):
        self.w("backend/runtime/consumer_core.py",
               "from aiokafka import AIOKafkaConsumer\n"
               "c = AIOKafkaConsumer('topic')\n")
        self.policy(runtime_paths=["backend/runtime"])
        self.assertEqual(gate.main([self.root]), 0)

    def test_known_unhandled_passes(self):
        self.w("backend/app/worker.py",
               "from aiokafka import AIOKafkaConsumer\n"
               "c = AIOKafkaConsumer('topic')\n")
        self.policy(known=["backend/app/worker.py:2"])
        self.assertEqual(gate.main([self.root]), 0)

    def test_baseline_pending_always_passes(self):
        self.w("backend/app/worker.py",
               "from aiokafka import AIOKafkaConsumer\n"
               "c = AIOKafkaConsumer('topic')\n")
        self.policy(mode="baseline-pending")
        self.assertEqual(gate.main([self.root]), 0)

    def test_report_mode_always_passes(self):
        self.w("backend/app/worker.py",
               "from aiokafka import AIOKafkaConsumer\n"
               "c = AIOKafkaConsumer('topic')\n")
        self.policy(mode="ratchet")
        self.assertEqual(gate.main([self.root, "--report"]), 0)


if __name__ == "__main__":
    unittest.main()
