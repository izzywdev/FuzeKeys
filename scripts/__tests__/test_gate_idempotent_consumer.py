"""gate-idempotent-consumer self-tests — the gate MUST be known to FAIL on a violation."""
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_SCRIPTS))

spec = importlib.util.spec_from_file_location(
    "gate_idempotent_consumer", _SCRIPTS / "gate_idempotent_consumer.py"
)
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)


def _write_policy(tmp: str, mode: str = "ratchet", known: list | None = None,
                  runtime_paths: list | None = None) -> None:
    gov = Path(tmp) / "governance"
    gov.mkdir(exist_ok=True)
    (gov / "idempotent-consumer-policy.json").write_text(json.dumps({
        "mode": mode,
        "runtimePaths": runtime_paths or [],
        "knownUnhandled": known or [],
    }))


class IdempotentConsumerViolationTests(unittest.TestCase):
    """Gate MUST exit 1 on a raw consumer instantiation in ratchet mode."""

    def test_aio_kafka_consumer_instantiation_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "consumer.py").write_text(
                "from aiokafka import AIOKafkaConsumer\n"
                "c = AIOKafkaConsumer('my-topic', bootstrap_servers='kafka:9092')\n"
            )
            _write_policy(tmp)
            policy = gate.load_policy(tmp, gate.GATE_KEY)
            violations = gate.find_violations(tmp, policy)
        self.assertTrue(len(violations) >= 1, "expected at least one violation")

    def test_kafka_consumer_class_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "sub.py").write_text("KafkaConsumer('topic', group_id='g')\n")
            _write_policy(tmp)
            policy = gate.load_policy(tmp, gate.GATE_KEY)
            violations = gate.find_violations(tmp, policy)
        self.assertTrue(len(violations) >= 1)

    def test_consumer_run_call_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "worker.py").write_text(
                "async def run(consumer):\n"
                "    await consumer.run()\n"
            )
            _write_policy(tmp)
            policy = gate.load_policy(tmp, gate.GATE_KEY)
            violations = gate.find_violations(tmp, policy)
        self.assertTrue(len(violations) >= 1)

    def test_main_exits_1_on_violation(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "bad.py").write_text("AIOKafkaConsumer()\n")
            _write_policy(tmp)
            code = gate.main([tmp])
        self.assertEqual(code, 1)

    def test_commented_line_is_not_a_violation(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "ok.py").write_text(
                "# AIOKafkaConsumer is wrapped by the shared runtime\n"
                "x = 1\n"
            )
            _write_policy(tmp)
            policy = gate.load_policy(tmp, gate.GATE_KEY)
            violations = gate.find_violations(tmp, policy)
        self.assertEqual(violations, [])


class IdempotentConsumerCleanTests(unittest.TestCase):
    """Gate MUST exit 0 on clean code."""

    def test_no_kafka_code_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "handler.py").write_text(
                "def handle_event(event):\n"
                "    return event\n"
            )
            _write_policy(tmp)
            code = gate.main([tmp])
        self.assertEqual(code, 0)

    def test_consumer_in_runtime_path_is_exempt(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = Path(tmp) / "runtime"
            runtime.mkdir()
            (runtime / "consumer_runtime.py").write_text("AIOKafkaConsumer()\n")
            _write_policy(tmp, runtime_paths=["runtime"])
            policy = gate.load_policy(tmp, gate.GATE_KEY)
            violations = gate.find_violations(tmp, policy)
        self.assertEqual(violations, [])

    def test_baseline_pending_exits_0_even_with_violation(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "bad.py").write_text("KafkaConsumer()\n")
            _write_policy(tmp, mode="baseline-pending")
            code = gate.main([tmp])
        self.assertEqual(code, 0)

    def test_report_mode_exits_0_even_with_violation(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "bad.py").write_text("AIOKafkaConsumer()\n")
            _write_policy(tmp)
            code = gate.main([tmp, "--report"])
        self.assertEqual(code, 0)

    def test_empty_repo_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            code = gate.main([tmp])
        self.assertEqual(code, 0)


class IdempotentConsumerRatchetTests(unittest.TestCase):
    """Ratchet invariants."""

    def test_known_violation_does_not_exit_1(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "bad.py").write_text("AIOKafkaConsumer()\n")
            _write_policy(tmp)
            policy = gate.load_policy(tmp, gate.GATE_KEY)
            violations = gate.find_violations(tmp, policy)
            self.assertEqual(len(violations), 1)
            _write_policy(tmp, known=violations)
            code = gate.main([tmp])
        self.assertEqual(code, 0)

    def test_fixed_known_entry_exits_1(self):
        with tempfile.TemporaryDirectory() as tmp:
            _write_policy(tmp, known=["some/file.py:3 — raw Kafka consumer outside shared runtime"])
            (Path(tmp) / "clean.py").write_text("pass\n")
            code = gate.main([tmp])
        self.assertEqual(code, 1)


if __name__ == "__main__":
    unittest.main()
