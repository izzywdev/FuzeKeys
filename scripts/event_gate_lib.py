"""Shared library for event-infrastructure gates.

Used by gate_event_envelope.py, gate_outbox.py, and gate_idempotent_consumer.py.

Policy format (governance/<name>-policy.json):
  {
    "mode": "baseline-pending" | "ratchet",
    "knownUnhandled": ["relpath", ...],
    ... gate-specific fields ...
  }

In baseline-pending mode: scan everything, warn, suggest a baseline, exit 0.
In ratchet mode:
  - New finding not in knownUnhandled → fail (exit 1)
  - Known finding in knownUnhandled → warn only
  - Entry in knownUnhandled that has no corresponding finding → fail (must be removed)
"""
from __future__ import annotations

import json
import os
import re
import subprocess

PRUNE_DIRS = {
    ".git", "node_modules", "dist", "build", ".venv", "venv", "__pycache__",
    "coverage", ".next", ".terraform", ".turbo", ".cache", "out", "target",
    "storybook-static", "playwright-report", "test-results",
}


def load_policy(root: str, name: str) -> dict:
    """Load governance/<name>-policy.json; return safe defaults when absent."""
    path = os.path.join(root, "governance", f"{name}-policy.json")
    if not os.path.isfile(path):
        return {"mode": "baseline-pending", "knownUnhandled": []}
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def tracked_source_files(root: str) -> list[str]:
    """Return tracked Python / TypeScript / JavaScript file paths under root."""
    try:
        res = subprocess.run(
            ["git", "-C", root, "ls-files", "--",
             "*.py", "*.ts", "*.js", "*.tsx", "*.jsx"],
            capture_output=True, text=True, timeout=60,
        )
        if res.returncode == 0 and res.stdout.strip():
            return [os.path.join(root, p) for p in res.stdout.splitlines() if p.strip()]
    except Exception:
        pass
    out: list[str] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in PRUNE_DIRS]
        for fn in filenames:
            if fn.endswith((".py", ".ts", ".js", ".tsx", ".jsx")):
                out.append(os.path.join(dirpath, fn))
    return out


def scan_for_patterns(
    root: str,
    patterns: list[str],
    exclude_paths: list[str] | None = None,
) -> list[tuple[str, int, str]]:
    """Scan tracked source files for regex patterns.

    Returns list of (relpath, lineno, line) tuples.
    exclude_paths entries are relative paths or prefixes (e.g. "backend/app/outbox").
    """
    exclude = list(exclude_paths or [])
    compiled = [re.compile(p) for p in patterns]
    hits: list[tuple[str, int, str]] = []

    for filepath in tracked_source_files(root):
        relpath = os.path.relpath(filepath, root).replace("\\", "/")
        if _is_excluded(relpath, exclude):
            continue
        try:
            with open(filepath, "r", encoding="utf-8", errors="ignore") as fh:
                for lineno, line in enumerate(fh, 1):
                    for pat in compiled:
                        if pat.search(line):
                            hits.append((relpath, lineno, line.rstrip()))
                            break
        except OSError:
            pass
    return hits


def _is_excluded(relpath: str, exclude: list[str]) -> bool:
    for ep in exclude:
        ep = ep.replace("\\", "/").rstrip("/")
        if relpath == ep or relpath.startswith(ep + "/"):
            return True
    return False


def run_ratchet(
    findings: list[tuple[str, int, str]],
    policy: dict,
    gate_name: str,
) -> int:
    """Apply ratchet logic and print results. Returns 0 (pass) or 1 (fail)."""
    mode = policy.get("mode", "baseline-pending")
    known: list[str] = list(policy.get("knownUnhandled", []) or [])
    finding_files = {relpath for relpath, _, _ in findings}

    if mode == "baseline-pending":
        if findings:
            print(
                f"::warning title={gate_name}::{len(findings)} finding(s) in "
                f"baseline-pending mode — not blocking"
            )
            for relpath, lineno, line in findings:
                print(f"  {relpath}:{lineno}: {line.strip()}")
            suggested = sorted(finding_files)
            print(
                f"\nSuggested knownUnhandled (set mode to 'ratchet' once these are "
                f"resolved or accepted):"
            )
            print(json.dumps(suggested, indent=2))
        else:
            print(f"{gate_name}: no findings (baseline-pending) — OK")
        return 0

    # ratchet mode
    stale = [k for k in known if k not in finding_files]
    new_violations = [(r, n, l) for r, n, l in findings if r not in known]
    known_violations = [(r, n, l) for r, n, l in findings if r in known]

    failed = False

    if stale:
        print(
            f"::error title={gate_name}::stale knownUnhandled entries "
            f"(now compliant — MUST be removed from the policy):"
        )
        for s in sorted(stale):
            print(f"  - {s}")
        failed = True

    if known_violations:
        print(
            f"::warning title={gate_name}::{len(known_violations)} known "
            f"violation(s) tracked in knownUnhandled:"
        )
        for relpath, lineno, line in known_violations:
            print(f"  {relpath}:{lineno}: {line.strip()}")

    if new_violations:
        print(f"::error title={gate_name}::{len(new_violations)} new violation(s):")
        for relpath, lineno, line in new_violations:
            print(f"  {relpath}:{lineno}: {line.strip()}")
        failed = True

    if not failed:
        if known_violations:
            print(
                f"{gate_name}: {len(known_violations)} known violation(s) in "
                f"knownUnhandled — OK (remove them once fixed)"
            )
        else:
            print(f"{gate_name}: no violations — OK")

    return 1 if failed else 0
