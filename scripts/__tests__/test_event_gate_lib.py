"""Tests for scripts/event_gate_lib.py.

Asserts the library's core mechanics behave correctly: file discovery, policy
loading, pattern scanning, and ratchet evaluation.  Every case below asserts
something non-trivial; a test that only verifies the happy-path proves nothing.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(REPO_ROOT, "scripts"))
import event_gate_lib  # noqa: E402


def make_git_repo() -> str:
    """Create a throwaway git repo in a temp directory and return its path."""
    d = tempfile.mkdtemp(prefix="egl-test-")
    subprocess.run(["git", "init", "-q", d], check=True)
    subprocess.run(
        ["git", "-C", d, "-c", "user.email=t@t", "-c", "user.name=t",
         "commit", "-q", "--allow-empty", "-m", "init"],
        check=True,
    )
    return d


def write_and_commit(root: str, rel: str, content: str) -> None:
    path = os.path.join(root, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    subprocess.run(["git", "-C", root, "add", rel], check=True)
    subprocess.run(
        ["git", "-C", root, "-c", "user.email=t@t", "-c", "user.name=t",
         "commit", "-q", "-m", "fixture"],
        check=True,
    )


class TestCandidateFiles(unittest.TestCase):
    def setUp(self):
        self.root = make_git_repo()
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)

    def test_tracked_python_file_is_returned(self):
        write_and_commit(self.root, "backend/app.py", "x = 1\n")
        files = event_gate_lib.candidate_files(self.root, extensions=(".py",))
        rels = [os.path.relpath(f, self.root).replace("\\", "/") for f in files]
        self.assertIn("backend/app.py", rels)

    def test_untracked_file_is_not_returned(self):
        path = os.path.join(self.root, "untracked.py")
        with open(path, "w") as f:
            f.write("x = 1\n")
        files = event_gate_lib.candidate_files(self.root, extensions=(".py",))
        rels = [os.path.relpath(f, self.root).replace("\\", "/") for f in files]
        self.assertNotIn("untracked.py", rels)

    def test_node_modules_are_pruned(self):
        write_and_commit(self.root, "node_modules/pkg/index.js", "module.exports = {}\n")
        files = event_gate_lib.candidate_files(self.root, extensions=(".js",))
        for f in files:
            self.assertNotIn("node_modules", f.replace("\\", "/"))


class TestLoadPolicy(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)

    def test_missing_policy_file_returns_strictest_posture(self):
        policy = event_gate_lib.load_policy(self.root, "governance/nonexistent.json")
        self.assertEqual(policy["mode"], "fail")
        self.assertEqual(policy["knownUnhandled"], [])

    def test_policy_file_is_loaded(self):
        gov = os.path.join(self.root, "governance")
        os.makedirs(gov, exist_ok=True)
        with open(os.path.join(gov, "test-policy.json"), "w") as f:
            json.dump({"mode": "warn", "knownUnhandled": ["a/b.py:10"]}, f)
        policy = event_gate_lib.load_policy(self.root, "governance/test-policy.json")
        self.assertEqual(policy["mode"], "warn")
        self.assertIn("a/b.py:10", policy["knownUnhandled"])

    def test_missing_keys_get_defaults(self):
        gov = os.path.join(self.root, "governance")
        os.makedirs(gov, exist_ok=True)
        with open(os.path.join(gov, "minimal.json"), "w") as f:
            json.dump({}, f)
        policy = event_gate_lib.load_policy(self.root, "governance/minimal.json")
        self.assertEqual(policy["mode"], "fail")
        self.assertEqual(policy["knownUnhandled"], [])


class TestScanLines(unittest.TestCase):
    def setUp(self):
        self.root = make_git_repo()
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)

    def test_pattern_match_is_returned(self):
        write_and_commit(self.root, "src/svc.py", "producer = AIOKafkaProducer()\n")
        files = event_gate_lib.candidate_files(self.root, extensions=(".py",))
        hits = event_gate_lib.scan_lines(files, [re.compile(r"AIOKafkaProducer")])
        self.assertEqual(len(hits), 1)
        self.assertIn("AIOKafkaProducer", hits[0][2])

    def test_commented_line_is_skipped(self):
        write_and_commit(self.root, "src/svc.py", "# producer = AIOKafkaProducer()\n")
        files = event_gate_lib.candidate_files(self.root, extensions=(".py",))
        hits = event_gate_lib.scan_lines(files, [re.compile(r"AIOKafkaProducer")])
        self.assertEqual(hits, [])

    def test_skip_path_re_suppresses_matching_files(self):
        write_and_commit(self.root, "outbox/relay.py", "producer = AIOKafkaProducer()\n")
        files = event_gate_lib.candidate_files(self.root, extensions=(".py",))
        skip = re.compile(r"/outbox/")
        hits = event_gate_lib.scan_lines(files, [re.compile(r"AIOKafkaProducer")], skip)
        self.assertEqual(hits, [])


class TestApplyRatchet(unittest.TestCase):
    def _make_hits(self, root: str) -> list[tuple[str, int, str]]:
        path = os.path.join(root, "backend", "svc.py")
        return [(path, 5, "    producer = AIOKafkaProducer()")]

    def test_fail_mode_with_no_known_produces_violation(self):
        with tempfile.TemporaryDirectory() as root:
            os.makedirs(os.path.join(root, "backend"), exist_ok=True)
            hits = self._make_hits(root)
            policy = {"mode": "fail", "knownUnhandled": []}
            violations, suppressed = event_gate_lib.apply_ratchet(hits, root, policy)
        self.assertEqual(len(violations), 1)
        self.assertEqual(suppressed, [])

    def test_warn_mode_suppresses_all_hits(self):
        with tempfile.TemporaryDirectory() as root:
            os.makedirs(os.path.join(root, "backend"), exist_ok=True)
            hits = self._make_hits(root)
            policy = {"mode": "warn", "knownUnhandled": []}
            violations, suppressed = event_gate_lib.apply_ratchet(hits, root, policy)
        self.assertEqual(violations, [])
        self.assertEqual(len(suppressed), 1)

    def test_known_unhandled_entry_suppresses_hit(self):
        with tempfile.TemporaryDirectory() as root:
            os.makedirs(os.path.join(root, "backend"), exist_ok=True)
            hits = self._make_hits(root)
            path, lineno, _ = hits[0]
            rel = os.path.relpath(path, root).replace("\\", "/")
            policy = {"mode": "fail", "knownUnhandled": [f"{rel}:{lineno}"]}
            violations, suppressed = event_gate_lib.apply_ratchet(hits, root, policy)
        self.assertEqual(violations, [])
        self.assertEqual(len(suppressed), 1)

    def test_moved_line_re_violates(self):
        """A knownUnhandled entry at :5 must not suppress the same code at :6."""
        with tempfile.TemporaryDirectory() as root:
            os.makedirs(os.path.join(root, "backend"), exist_ok=True)
            path = os.path.join(root, "backend", "svc.py")
            hits = [(path, 6, "    producer = AIOKafkaProducer()")]
            rel = os.path.relpath(path, root).replace("\\", "/")
            policy = {"mode": "fail", "knownUnhandled": [f"{rel}:5"]}
            violations, suppressed = event_gate_lib.apply_ratchet(hits, root, policy)
        self.assertEqual(len(violations), 1)
        self.assertEqual(suppressed, [])


if __name__ == "__main__":
    unittest.main()
