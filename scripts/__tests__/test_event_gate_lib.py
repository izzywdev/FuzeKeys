"""Self-tests for event_gate_lib — the shared Policy/Finding/evaluate helpers.

Each test asserts the ratchet logic is correct:
  - new offenders in ratchet mode       -> exit 1
  - known-unhandled in ratchet mode     -> exit 0 (warning only)
  - stale known-unhandled entries       -> exit 1
  - baseline-pending always             -> exit 0
  - report_mode always                  -> exit 0
"""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import event_gate_lib as lib


def _write_policy(path: str, mode: str, known=None) -> lib.Policy:
    data = {"mode": mode, "knownUnhandled": known or []}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f)
    return lib.Policy(path)


class PolicyTests(unittest.TestCase):
    def test_missing_policy_defaults_to_ratchet(self):
        p = lib.Policy("/nonexistent/policy.json")
        self.assertEqual(p.mode, "ratchet")

    def test_missing_policy_has_empty_known_unhandled(self):
        p = lib.Policy("/nonexistent/policy.json")
        self.assertEqual(p.known_unhandled, [])

    def test_baseline_pending_flag(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({"mode": "baseline-pending", "knownUnhandled": []}, f)
            fname = f.name
        try:
            p = lib.Policy(fname)
            self.assertTrue(p.is_baseline_pending)
        finally:
            os.unlink(fname)

    def test_ratchet_flag(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({"mode": "ratchet", "knownUnhandled": []}, f)
            fname = f.name
        try:
            p = lib.Policy(fname)
            self.assertFalse(p.is_baseline_pending)
        finally:
            os.unlink(fname)


class EvaluateTests(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()

    def _file(self, rel: str) -> str:
        path = os.path.join(self.root, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        return path

    def _policy(self, mode: str, known=None) -> lib.Policy:
        pfile = os.path.join(self.root, "policy.json")
        return _write_policy(pfile, mode, known)

    def test_new_offender_fails_in_ratchet(self):
        policy = self._policy("ratchet")
        f = lib.Finding(self._file("app/consumer.py"), 5, "raw consumer")
        rc = lib.evaluate([f], policy, self.root, "gate-test")
        self.assertEqual(rc, 1)

    def test_known_unhandled_passes_in_ratchet(self):
        policy = self._policy("ratchet", known=["app/consumer.py:5"])
        f = lib.Finding(self._file("app/consumer.py"), 5, "raw consumer")
        rc = lib.evaluate([f], policy, self.root, "gate-test")
        self.assertEqual(rc, 0)

    def test_stale_known_unhandled_fails_in_ratchet(self):
        policy = self._policy("ratchet", known=["app/nonexistent.py:1"])
        rc = lib.evaluate([], policy, self.root, "gate-test")
        self.assertEqual(rc, 1)

    def test_baseline_pending_always_passes(self):
        policy = self._policy("baseline-pending")
        f = lib.Finding(self._file("app/consumer.py"), 5, "raw consumer")
        rc = lib.evaluate([f], policy, self.root, "gate-test")
        self.assertEqual(rc, 0)

    def test_report_mode_always_passes(self):
        policy = self._policy("ratchet")
        f = lib.Finding(self._file("app/consumer.py"), 5, "raw consumer")
        rc = lib.evaluate([f], policy, self.root, "gate-test", report_mode=True)
        self.assertEqual(rc, 0)

    def test_no_findings_passes(self):
        policy = self._policy("ratchet")
        rc = lib.evaluate([], policy, self.root, "gate-test")
        self.assertEqual(rc, 0)

    def test_finding_key_uses_relative_path(self):
        f = lib.Finding(os.path.join(self.root, "app", "worker.py"), 10, "msg")
        self.assertEqual(f.key(self.root), "app/worker.py:10")


if __name__ == "__main__":
    unittest.main()
