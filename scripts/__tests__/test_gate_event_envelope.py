"""gate-event-envelope self-tests — the gate MUST be known to FAIL on a violation."""
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_SCRIPTS))

spec = importlib.util.spec_from_file_location(
    "gate_event_envelope", _SCRIPTS / "gate_event_envelope.py"
)
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)


def _write_policy(tmp: str, mode: str = "ratchet", known: list | None = None,
                  registry_paths: list | None = None) -> None:
    gov = Path(tmp) / "governance"
    gov.mkdir(exist_ok=True)
    (gov / "event-envelope-policy.json").write_text(json.dumps({
        "mode": mode,
        "registryPaths": registry_paths or [],
        "knownUnhandled": known or [],
    }))


_V2_EVENT = """\
class UserCreatedEvent:
    eventId: str
    aggregateId: str
    aggregateType: str
    aggregateVersion: int
    user_id: str
"""

_INCOMPLETE_EVENT = """\
class UserCreatedEvent:
    aggregate_id: str
    aggregate_type: str
    # missing eventId and aggregateVersion
    user_id: str
"""


class EventEnvelopeViolationTests(unittest.TestCase):
    """Gate MUST exit 1 on an event schema that lacks v2 fields in ratchet mode."""

    def test_missing_event_id_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            events_dir = Path(tmp) / "events"
            events_dir.mkdir()
            (events_dir / "user_events.py").write_text(_INCOMPLETE_EVENT)
            _write_policy(tmp, registry_paths=["events"])
            policy = gate.load_policy(tmp, gate.GATE_KEY)
            violations = gate.find_violations(tmp, policy)
        self.assertTrue(len(violations) >= 1, f"expected violations, got: {violations}")

    def test_main_exits_1_on_violation(self):
        with tempfile.TemporaryDirectory() as tmp:
            events_dir = Path(tmp) / "events"
            events_dir.mkdir()
            (events_dir / "ev.py").write_text(_INCOMPLETE_EVENT)
            _write_policy(tmp, registry_paths=["events"])
            code = gate.main([tmp])
        self.assertEqual(code, 1)


class EventEnvelopeCleanTests(unittest.TestCase):
    """Gate MUST exit 0 on correct schemas and when no events are registered."""

    def test_no_registry_paths_passes_vacuously(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "service.py").write_text("x = 1\n")
            # No registryPaths → vacuous pass
            _write_policy(tmp, registry_paths=[])
            code = gate.main([tmp])
        self.assertEqual(code, 0)

    def test_no_policy_file_passes_vacuously(self):
        # Absent policy → baseline-pending with empty registryPaths
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "ev.py").write_text(_INCOMPLETE_EVENT)
            code = gate.main([tmp])
        self.assertEqual(code, 0)

    def test_compliant_v2_event_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            events_dir = Path(tmp) / "events"
            events_dir.mkdir()
            (events_dir / "user_events.py").write_text(_V2_EVENT)
            _write_policy(tmp, registry_paths=["events"])
            code = gate.main([tmp])
        self.assertEqual(code, 0)

    def test_baseline_pending_exits_0_even_with_violation(self):
        with tempfile.TemporaryDirectory() as tmp:
            events_dir = Path(tmp) / "events"
            events_dir.mkdir()
            (events_dir / "ev.py").write_text(_INCOMPLETE_EVENT)
            _write_policy(tmp, mode="baseline-pending", registry_paths=["events"])
            code = gate.main([tmp])
        self.assertEqual(code, 0)

    def test_report_mode_exits_0_even_with_violation(self):
        with tempfile.TemporaryDirectory() as tmp:
            events_dir = Path(tmp) / "events"
            events_dir.mkdir()
            (events_dir / "ev.py").write_text(_INCOMPLETE_EVENT)
            _write_policy(tmp, registry_paths=["events"])
            code = gate.main([tmp, "--report"])
        self.assertEqual(code, 0)

    def test_empty_repo_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            code = gate.main([tmp])
        self.assertEqual(code, 0)


class EventEnvelopeRatchetTests(unittest.TestCase):
    """Ratchet invariants."""

    def test_known_violation_does_not_exit_1(self):
        with tempfile.TemporaryDirectory() as tmp:
            events_dir = Path(tmp) / "events"
            events_dir.mkdir()
            (events_dir / "ev.py").write_text(_INCOMPLETE_EVENT)
            _write_policy(tmp, registry_paths=["events"])
            policy = gate.load_policy(tmp, gate.GATE_KEY)
            violations = gate.find_violations(tmp, policy)
            self.assertGreater(len(violations), 0)
            _write_policy(tmp, known=violations, registry_paths=["events"])
            code = gate.main([tmp])
        self.assertEqual(code, 0)

    def test_fixed_known_entry_exits_1(self):
        with tempfile.TemporaryDirectory() as tmp:
            events_dir = Path(tmp) / "events"
            events_dir.mkdir()
            # Compliant event but knownUnhandled still lists an old violation
            (events_dir / "ev.py").write_text(_V2_EVENT)
            _write_policy(
                tmp,
                known=["events/ev.py — event schema missing required v2 field 'eventId' / 'event_id'"],
                registry_paths=["events"],
            )
            code = gate.main([tmp])
        self.assertEqual(code, 1)


if __name__ == "__main__":
    unittest.main()
