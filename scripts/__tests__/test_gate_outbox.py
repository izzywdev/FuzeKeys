"""gate-outbox self-tests — the gate MUST be known to FAIL on a violation."""
import importlib.util
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_SCRIPTS))

spec = importlib.util.spec_from_file_location("gate_outbox", _SCRIPTS / "gate_outbox.py")
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)


def _write_policy(tmp: str, mode: str = "ratchet", known: list | None = None,
                  runtime_paths: list | None = None) -> None:
    gov = Path(tmp) / "governance"
    gov.mkdir(exist_ok=True)
    (gov / "outbox-policy.json").write_text(json.dumps({
        "mode": mode,
        "runtimePaths": runtime_paths or [],
        "knownUnhandled": known or [],
    }))


class OutboxGateViolationTests(unittest.TestCase):
    """Gate MUST exit 1 on a direct producer call in ratchet mode."""

    def test_aio_kafka_producer_instantiation_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "producer.py").write_text(
                "from aiokafka import AIOKafkaProducer\n"
                "p = AIOKafkaProducer(bootstrap_servers='kafka:9092')\n"
            )
            _write_policy(tmp)
            policy = gate.load_policy(tmp, gate.GATE_KEY)
            violations = gate.find_violations(tmp, policy)
        self.assertTrue(len(violations) >= 1, "expected at least one violation")

    def test_kafka_producer_class_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "pub.py").write_text("KafkaProducer(bootstrap_servers='localhost')\n")
            _write_policy(tmp)
            policy = gate.load_policy(tmp, gate.GATE_KEY)
            violations = gate.find_violations(tmp, policy)
        self.assertTrue(len(violations) >= 1)

    def test_producer_send_call_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "emit.py").write_text(
                "async def publish(producer, msg):\n"
                "    await producer.send('my-topic', msg)\n"
            )
            _write_policy(tmp)
            policy = gate.load_policy(tmp, gate.GATE_KEY)
            violations = gate.find_violations(tmp, policy)
        self.assertTrue(len(violations) >= 1)

    def test_main_exits_1_on_violation(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "bad.py").write_text("AIOKafkaProducer()\n")
            _write_policy(tmp)
            code = gate.main([tmp])
        self.assertEqual(code, 1)

    def test_commented_line_is_not_a_violation(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "ok.py").write_text(
                "# AIOKafkaProducer is used in the relay only\n"
                "x = 1\n"
            )
            _write_policy(tmp)
            policy = gate.load_policy(tmp, gate.GATE_KEY)
            violations = gate.find_violations(tmp, policy)
        self.assertEqual(violations, [])


class OutboxGateCleanTests(unittest.TestCase):
    """Gate MUST exit 0 on clean code."""

    def test_no_kafka_code_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "service.py").write_text(
                "def save_entity(db, entity):\n"
                "    db.add(entity)\n"
                "    db.commit()\n"
            )
            _write_policy(tmp)
            code = gate.main([tmp])
        self.assertEqual(code, 0)

    def test_producer_in_runtime_path_is_exempt(self):
        with tempfile.TemporaryDirectory() as tmp:
            relay = Path(tmp) / "outbox"
            relay.mkdir()
            (relay / "relay.py").write_text("AIOKafkaProducer()\n")
            _write_policy(tmp, runtime_paths=["outbox"])
            policy = gate.load_policy(tmp, gate.GATE_KEY)
            violations = gate.find_violations(tmp, policy)
        self.assertEqual(violations, [])

    def test_baseline_pending_exits_0_even_with_violation(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "bad.py").write_text("KafkaProducer()\n")
            _write_policy(tmp, mode="baseline-pending")
            code = gate.main([tmp])
        self.assertEqual(code, 0)

    def test_report_mode_exits_0_even_with_violation(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "bad.py").write_text("AIOKafkaProducer()\n")
            _write_policy(tmp)
            code = gate.main([tmp, "--report"])
        self.assertEqual(code, 0)

    def test_empty_repo_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            code = gate.main([tmp])
        self.assertEqual(code, 0)


class OutboxRatchetTests(unittest.TestCase):
    """Ratchet invariants: known entries warn; fixed entries must be removed."""

    def test_known_violation_does_not_exit_1(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "bad.py").write_text("AIOKafkaProducer()\n")
            # First, discover what the violation string looks like
            _write_policy(tmp)
            policy = gate.load_policy(tmp, gate.GATE_KEY)
            violations = gate.find_violations(tmp, policy)
            self.assertEqual(len(violations), 1)
            # Now add it to knownUnhandled
            _write_policy(tmp, known=violations)
            code = gate.main([tmp])
        self.assertEqual(code, 0)

    def test_fixed_known_entry_exits_1(self):
        with tempfile.TemporaryDirectory() as tmp:
            # No actual violation but knownUnhandled lists one
            _write_policy(tmp, known=["some/file.py:5 — direct Kafka producer call outside outbox relay"])
            (Path(tmp) / "clean.py").write_text("pass\n")
            code = gate.main([tmp])
        self.assertEqual(code, 1)


if __name__ == "__main__":
    unittest.main()
