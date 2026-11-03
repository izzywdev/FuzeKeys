#!/usr/bin/env python3
"""event_gate_lib — shared library for data-consistency event gates.

Provides policy loading, code scanning, and reporting utilities used by
gate_event_envelope, gate_outbox, and gate_idempotent_consumer.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
from typing import Any


# ── Policy ───────────────────────────────────────────────────────────────────

DEFAULT_POLICY: dict[str, Any] = {"mode": "baseline-pending", "knownUnhandled": []}
MODES = {"baseline-pending", "ratchet"}


def load_policy(root: str, gate_name: str) -> dict[str, Any]:
    """Load governance/<gate_name>-policy.json; return DEFAULT_POLICY if absent."""
    fname = gate_name.replace("gate-", "").replace("_", "-") + "-policy.json"
    path = os.path.join(root, "governance", fname)
    if not os.path.isfile(path):
        return dict(DEFAULT_POLICY)
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return dict(DEFAULT_POLICY)
        mode = data.get("mode", "baseline-pending")
        if mode not in MODES:
            mode = "baseline-pending"
        known = data.get("knownUnhandled", [])
        if not isinstance(known, list):
            known = []
        return {"mode": mode, "knownUnhandled": list(known)}
    except Exception:
        return dict(DEFAULT_POLICY)


# ── File enumeration ──────────────────────────────────────────────────────────

PRUNE_DIRS = {
    ".git", "node_modules", "dist", "build", ".venv", "venv", "vendor",
    "__pycache__", "coverage", ".next", ".terraform", ".turbo", ".cache",
    "out", "target", "storybook-static", "playwright-report", "test-results",
    "migrations", "alembic", "modules",
}


def tracked_files(root: str, *extensions: str) -> list[str]:
    """Return git-tracked files with given extensions; fall back to os.walk."""
    pats = [f"*{e}" for e in extensions] + [f"**/*{e}" for e in extensions]
    try:
        res = subprocess.run(
            ["git", "-C", root, "ls-files", "--"] + pats,
            capture_output=True, text=True, timeout=60,
        )
        if res.returncode == 0 and res.stdout.strip():
            return [
                os.path.join(root, p)
                for p in res.stdout.splitlines()
                if p.strip()
                and not any(
                    seg in PRUNE_DIRS
                    for seg in p.replace("\\", "/").split("/")
                )
            ]
    except Exception:
        pass
    out: list[str] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in PRUNE_DIRS]
        for fn in filenames:
            if any(fn.endswith(e) for e in extensions):
                out.append(os.path.join(dirpath, fn))
    return out


def read_lines(path: str) -> list[tuple[int, str]]:
    """Return (line_number, line) pairs, 1-indexed."""
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            return [(i + 1, line) for i, line in enumerate(f)]
    except OSError:
        return []


# ── Ratchet evaluation ────────────────────────────────────────────────────────

class GateResult:
    """Accumulate findings and evaluate against a policy."""

    def __init__(self, gate_name: str, policy: dict[str, Any]) -> None:
        self.gate_name = gate_name
        self.policy = policy
        self.findings: list[str] = []

    def add(self, finding: str) -> None:
        self.findings.append(finding)

    def evaluate(self, report_only: bool = False) -> int:
        """Return exit code: 0 = pass, 1 = fail."""
        mode = self.policy["mode"]
        known = set(self.policy.get("knownUnhandled", []))
        found = set(self.findings)

        if mode == "baseline-pending":
            if found:
                print(
                    f"::warning title={self.gate_name}::{len(found)} finding(s) "
                    "(baseline-pending — warnings only; flip policy to 'ratchet' to enforce)"
                )
                for item in sorted(found):
                    print(f"  - {item}")
                self._suggest_baseline(found)
            else:
                print(f"{self.gate_name}: no findings. OK (baseline-pending)")
            return 0

        # ratchet mode
        exit_code = 0

        # Stale known entries (the violation is now gone) must be removed.
        stale = known - found
        for s in sorted(stale):
            print(
                f"::error title={self.gate_name}::[stale] {s!r} is listed in "
                "knownUnhandled but the violation is gone — remove it from the policy."
            )
            exit_code = 1

        # New violations (not in knownUnhandled) → hard fail.
        for v in sorted(found - known):
            print(f"::error title={self.gate_name}::[new] {v}")
            exit_code = 1

        # Known violations still present → warn only.
        for v in sorted(found & known):
            print(f"::warning title={self.gate_name}::[known] {v}")

        if not report_only:
            if exit_code == 0:
                print(f"{self.gate_name}: OK")
        return exit_code if not report_only else 0

    def _suggest_baseline(self, found: set[str]) -> None:
        name = self.gate_name.replace("gate-", "").replace("_", "-")
        print(
            f"\n{self.gate_name}: suggested knownUnhandled baseline "
            f"(copy into governance/{name}-policy.json):"
        )
        print(json.dumps({"mode": "ratchet", "knownUnhandled": sorted(found)}, indent=2))
