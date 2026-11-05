#!/usr/bin/env python3
"""Shared utilities for event-domain gates.

Used by gate_outbox.py, gate_event_envelope.py, and gate_idempotent_consumer.py.
Not a standalone executable — import only.

Design conventions shared with the rest of the gate family:
  - `git ls-files` for file discovery; os.walk fallback when git is unavailable.
  - Missing policy file → strictest posture (mode=fail, empty knownUnhandled).
    Deleting a policy file must never be a way to silence a gate.
  - Commented-out lines (# / //) are skipped during pattern scanning so a
    legitimate comment mentioning AIOKafkaProducer doesn't fire the gate.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys

PRUNE_DIRS = {
    ".git", "node_modules", "dist", "build", ".venv", "venv", "vendor",
    "__pycache__", "coverage", ".next", ".terraform", ".turbo", ".cache",
    "out", "target", "storybook-static", "playwright-report", "test-results",
}


# ---------------------------------------------------------------------------
# File discovery
# ---------------------------------------------------------------------------

def candidate_files(root: str, extensions: tuple[str, ...] = (".py", ".ts", ".tsx", ".js", ".jsx")) -> list[str]:
    """Return tracked source files; falls back to os.walk when git is absent.

    When git is available and returns successfully, its output is authoritative —
    even an empty result means "no tracked files matching these patterns", and the
    os.walk fallback must NOT run (it would include untracked files).
    """
    try:
        res = subprocess.run(
            ["git", "-C", root, "ls-files", "--"] + [f"*{ext}" for ext in extensions],
            capture_output=True, text=True, timeout=60,
        )
        if res.returncode == 0:
            # git succeeded — use its output, even if empty.
            files = [os.path.join(root, p) for p in res.stdout.splitlines() if p.strip()]
            return [
                f for f in files
                if not any(seg in PRUNE_DIRS for seg in f.replace("\\", "/").split("/"))
            ]
    except Exception:
        pass
    out: list[str] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in PRUNE_DIRS]
        for fn in filenames:
            if any(fn.endswith(ext) for ext in extensions):
                out.append(os.path.join(dirpath, fn))
    return out


# ---------------------------------------------------------------------------
# Policy loading
# ---------------------------------------------------------------------------

def load_policy(root: str, policy_rel: str) -> dict:
    """Load a gate policy file.

    Missing file → {"mode": "fail", "knownUnhandled": []}.
    This is intentional: an absent file is the strictest posture, not "no policy".
    """
    path = os.path.join(root, policy_rel)
    if not os.path.isfile(path):
        return {"mode": "fail", "knownUnhandled": []}
    try:
        with open(path, encoding="utf-8") as f:
            policy = json.load(f)
    except Exception as exc:
        print(f"event_gate_lib: cannot parse {path}: {exc}", file=sys.stderr)
        return {"mode": "fail", "knownUnhandled": []}
    policy.setdefault("mode", "fail")
    policy.setdefault("knownUnhandled", [])
    return policy


# ---------------------------------------------------------------------------
# Pattern scanning
# ---------------------------------------------------------------------------

def scan_lines(
    files: list[str],
    patterns: list[re.Pattern],
    skip_path_re: re.Pattern | None = None,
) -> list[tuple[str, int, str]]:
    """Scan files for regex patterns.

    Returns list of (absolute_path, line_number, line_text) for each match.
    Skips commented-out lines (Python # and JS/TS //).
    Skips file paths matching skip_path_re.
    """
    hits: list[tuple[str, int, str]] = []
    for path in files:
        norm = path.replace("\\", "/")
        if skip_path_re and skip_path_re.search(norm):
            continue
        try:
            with open(path, encoding="utf-8", errors="ignore") as f:
                for lineno, raw in enumerate(f, 1):
                    stripped = raw.lstrip()
                    if stripped.startswith(("#", "//", "*")):
                        continue
                    for pat in patterns:
                        if pat.search(raw):
                            hits.append((path, lineno, raw.rstrip()))
                            break
        except OSError:
            continue
    return hits


# ---------------------------------------------------------------------------
# Ratchet / allowlist
# ---------------------------------------------------------------------------

def apply_ratchet(
    hits: list[tuple[str, int, str]],
    root: str,
    policy: dict,
) -> tuple[list[tuple[str, int, str]], list[tuple[str, int, str]]]:
    """Split hits into (violations, suppressed).

    mode=warn  → all hits suppressed (gate reports, never fails).
    mode=fail  → hits in knownUnhandled are suppressed; everything else is a violation.
                 A knownUnhandled entry may be "rel/path.py" (file) or
                 "rel/path.py:42" (specific line).  A line that MOVES re-violates.
    """
    mode = policy.get("mode", "fail")
    if mode == "warn":
        return [], list(hits)

    known: set[str] = set(policy.get("knownUnhandled", []))
    violations: list[tuple[str, int, str]] = []
    suppressed: list[tuple[str, int, str]] = []
    for hit in hits:
        path, lineno, line = hit
        rel = os.path.relpath(path, root).replace("\\", "/")
        if rel in known or f"{rel}:{lineno}" in known:
            suppressed.append(hit)
        else:
            violations.append(hit)
    return violations, suppressed


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

def rel(root: str, path: str) -> str:
    return os.path.relpath(path, root).replace("\\", "/")


def suggest_ratchet(hits: list[tuple[str, int, str]], root: str) -> list[str]:
    """Return knownUnhandled entries suitable for pasting into the policy file."""
    return [f"{rel(root, p)}:{n}" for p, n, _ in hits]
