"""Tests for event_gate_lib — the shared ratchet logic for data-consistency gates."""
import importlib.util
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

# Load event_gate_lib from scripts/ regardless of CWD
_SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_SCRIPTS))

spec = importlib.util.spec_from_file_location("event_gate_lib", _SCRIPTS / "event_gate_lib.py")
lib = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lib)


class LoadPolicyTests(unittest.TestCase):
    def test_absent_policy_returns_baseline_pending(self):
        with tempfile.TemporaryDirectory() as tmp:
            policy = lib.load_policy(tmp, "outbox")
        self.assertEqual(policy["mode"], "baseline-pending")
        self.assertEqual(policy["knownUnhandled"], [])

    def test_present_policy_is_loaded(self):
        with tempfile.TemporaryDirectory() as tmp:
            gov = Path(tmp) / "governance"
            gov.mkdir()
            (gov / "outbox-policy.json").write_text(
                json.dumps({"mode": "ratchet", "knownUnhandled": ["a:1 — x"]})
            )
            policy = lib.load_policy(tmp, "outbox")
        self.assertEqual(policy["mode"], "ratchet")
        self.assertIn("a:1 — x", policy["knownUnhandled"])

    def test_invalid_json_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            gov = Path(tmp) / "governance"
            gov.mkdir()
            (gov / "outbox-policy.json").write_text("not json {{{")
            with self.assertRaises(Exception):
                lib.load_policy(tmp, "outbox")


class ApplyRatchetTests(unittest.TestCase):
    def test_baseline_pending_always_exits_0(self):
        policy = {"mode": "baseline-pending", "knownUnhandled": []}
        # violations present — still exit 0
        code = lib.apply_ratchet(["a:1 — x", "b:2 — y"], policy, "gate-outbox")
        self.assertEqual(code, 0)

    def test_baseline_pending_no_violations_exits_0(self):
        policy = {"mode": "baseline-pending", "knownUnhandled": []}
        code = lib.apply_ratchet([], policy, "gate-outbox")
        self.assertEqual(code, 0)

    def test_report_mode_always_exits_0(self):
        policy = {"mode": "ratchet", "knownUnhandled": []}
        code = lib.apply_ratchet(["a:1 — x"], policy, "gate-outbox", report_mode=True)
        self.assertEqual(code, 0)

    def test_ratchet_new_violation_exits_1(self):
        policy = {"mode": "ratchet", "knownUnhandled": []}
        code = lib.apply_ratchet(["a:1 — new violation"], policy, "gate-outbox")
        self.assertEqual(code, 1)

    def test_ratchet_known_violation_still_present_exits_0(self):
        v = "a:1 — known violation"
        policy = {"mode": "ratchet", "knownUnhandled": [v]}
        code = lib.apply_ratchet([v], policy, "gate-outbox")
        self.assertEqual(code, 0)

    def test_ratchet_known_violation_now_fixed_exits_1(self):
        # Entry in knownUnhandled but no longer in violations → must remove it
        v = "a:1 — fixed violation"
        policy = {"mode": "ratchet", "knownUnhandled": [v]}
        code = lib.apply_ratchet([], policy, "gate-outbox")
        self.assertEqual(code, 1)

    def test_ratchet_no_violations_exits_0(self):
        policy = {"mode": "ratchet", "knownUnhandled": []}
        code = lib.apply_ratchet([], policy, "gate-outbox")
        self.assertEqual(code, 0)

    def test_missing_mode_defaults_to_baseline_pending(self):
        policy = {"knownUnhandled": []}  # no "mode" key
        code = lib.apply_ratchet(["a:1 — x"], policy, "gate-outbox")
        self.assertEqual(code, 0)


class GitTrackedPyFilesTests(unittest.TestCase):
    def test_fallback_finds_py_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "foo.py").write_text("x = 1")
            sub = Path(tmp) / "sub"
            sub.mkdir()
            (sub / "bar.py").write_text("y = 2")
            # No git repo — will use fallback os.walk
            files = lib.git_tracked_py_files(tmp)
        relpaths = {os.path.relpath(f, tmp).replace("\\", "/") for f in files}
        self.assertIn("foo.py", relpaths)
        self.assertIn("sub/bar.py", relpaths)

    def test_prune_dirs_excluded(self):
        with tempfile.TemporaryDirectory() as tmp:
            nm = Path(tmp) / "node_modules"
            nm.mkdir()
            (nm / "evil.py").write_text("import os")
            (Path(tmp) / "good.py").write_text("pass")
            files = lib.git_tracked_py_files(tmp)
        relpaths = {os.path.relpath(f, tmp).replace("\\", "/") for f in files}
        self.assertIn("good.py", relpaths)
        self.assertNotIn("node_modules/evil.py", relpaths)


if __name__ == "__main__":
    unittest.main()
