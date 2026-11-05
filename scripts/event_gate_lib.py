#!/usr/bin/env python3
"""Shared ratchet library for data-consistency event gates.

Used by gate_event_envelope, gate_outbox, gate_idempotent_consumer.
Policy shape (governance/<gate-key>-policy.json):
  {
    "mode": "baseline-pending"  | "ratchet",
    "knownUnhandled": ["relpath:line — reason", ...],
    ...gate-specific keys...
  }

Absent policy file  → mode "baseline-pending" (the seeded default).
mode baseline-pending → scan, warn, suggest baseline, exit 0.
mode ratchet          → new violations exit 1; known debt warns; fixed debt
                        (in knownUnhandled but no longer a violation) exits 1
                        (shrink-only ratchet).
"""
from __future__ import annotations

import json
import os
import subprocess

PRUNE_DIRS = frozenset({
    ".git", "node_modules", "dist", "build", ".venv", "venv", "vendor",
    "__pycache__", "coverage", ".next", ".terraform", ".turbo", ".cache",
    "out", "target", "storybook-static", "playwright-report", "test-results",
    "agent-templates", "modules",
})


# ---------------------------------------------------------------------------
# Policy
# ---------------------------------------------------------------------------

def load_policy(root: str, gate_key: str) -> dict:
    """Load governance/<gate_key>-policy.json; return baseline-pending default if absent."""
    path = os.path.join(root, "governance", f"{gate_key}-policy.json")
    if not os.path.isfile(path):
        return {"mode": "baseline-pending", "knownUnhandled": []}
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, dict):
        raise ValueError(f"{path}: expected a JSON object, got {type(data).__name__}")
    return data


# ---------------------------------------------------------------------------
# File discovery
# ---------------------------------------------------------------------------

def git_tracked_py_files(root: str) -> list[str]:
    """Return absolute paths of git-tracked .py files under root (prune dirs excluded)."""
    try:
        res = subprocess.run(
            ["git", "-C", root, "ls-files", "--", "*.py"],
            capture_output=True, text=True, timeout=60,
        )
        if res.returncode == 0 and res.stdout.strip():
            out = []
            for rel in res.stdout.splitlines():
                rel = rel.strip()
                if not rel:
                    continue
                parts = rel.replace("\\", "/").split("/")
                if any(p in PRUNE_DIRS for p in parts):
                    continue
                out.append(os.path.join(root, rel))
            return out
    except Exception:
        pass
    # Fallback: os.walk
    out = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in PRUNE_DIRS]
        for fn in filenames:
            if fn.endswith(".py"):
                out.append(os.path.join(dirpath, fn))
    return out


# ---------------------------------------------------------------------------
# Ratchet logic
# ---------------------------------------------------------------------------

def apply_ratchet(
    violations: list[str],
    policy: dict,
    gate_name: str,
    report_mode: bool = False,
) -> int:
    """Print results and return exit code (0 = pass, 1 = fail).

    report_mode: always exits 0 (verbose diagnostic used before the enforcing run).
    """
    mode = policy.get("mode", "baseline-pending")
    known: list[str] = list(policy.get("knownUnhandled", []) or [])

    # --report always exits 0 — it is a diagnostic step, not an enforcing one.
    if report_mode:
        if violations:
            print(f"{gate_name} --report: {len(violations)} finding(s)")
            for v in violations:
                marker = " [known]" if v in known else " [NEW]"
                print(f"  - {v}{marker}")
            new_v = [v for v in violations if v not in known]
            if new_v:
                print(f"\n# Suggested knownUnhandled entries for governance/{gate_name.replace('gate-','')}-policy.json:")
                for v in sorted(set(new_v)):
                    print(f'    "{v}"')
        else:
            print(f"{gate_name} --report: no findings")
        return 0

    if mode == "baseline-pending":
        if violations:
            print(f"::warning title={gate_name}::baseline-pending — {len(violations)} finding(s), exit 0")
            for v in violations:
                print(f"  - {v}")
            print(
                f"\n{gate_name}: baseline-pending mode — set mode:\"ratchet\" in "
                f"governance/{gate_name.replace('gate-', '')}-policy.json to enforce"
            )
        else:
            print(f"{gate_name}: no findings (baseline-pending)")
        return 0

    # mode == "ratchet"
    new_v = [v for v in violations if v not in known]
    still_known = [v for v in known if v in violations]
    fixed = [v for v in known if v not in violations]

    exit_code = 0

    if fixed:
        print(
            f"::error title={gate_name}::{len(fixed)} knownUnhandled "
            "entries are now compliant — remove them from the policy file:"
        )
        for f in fixed:
            print(f"  - {f}")
        exit_code = 1

    if new_v:
        print(f"::error title={gate_name}::{len(new_v)} new violation(s):")
        for v in new_v:
            print(f"  - {v}")
        exit_code = 1

    if still_known:
        print(
            f"::warning title={gate_name}::{len(still_known)} "
            "known-unhandled (shrink this list):"
        )
        for v in still_known:
            print(f"  - {v}")

    if exit_code == 0:
        print(f"{gate_name}: OK (ratchet — {len(violations)} violation(s), "
              f"{len(still_known)} known, {len(fixed)} fixed)")
    return exit_code
