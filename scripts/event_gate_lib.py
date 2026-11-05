#!/usr/bin/env python3
"""
Shared library for event-consistency gates.

Provides: Policy, Finding, evaluate(), ls_files().

Data-consistency-standard.md §3, §4, §11.
"""
from __future__ import annotations
import json
import os
import subprocess
from typing import List, NamedTuple

PRUNE_DIRS = {
    ".git", "node_modules", "dist", "build", ".venv", "venv", "vendor",
    "__pycache__", "coverage", ".next", ".terraform", ".turbo", ".cache",
    "out", "target", "storybook-static", "playwright-report", "test-results",
}


class Policy:
    """Read a gate policy file; fail-closed when absent."""

    def __init__(self, path: "str | None" = None, default_mode: str = "ratchet"):
        if path and os.path.isfile(path):
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        else:
            # Fail-closed: missing policy file = strictest mode.
            data = {}
        self.mode: str = data.get("mode", default_mode)
        self.known_unhandled: List[str] = data.get("knownUnhandled", [])
        # Additional fields used by specific gates
        self.registry_paths: List[str] = data.get("registryPaths", [])
        self.allowed_producer_paths: List[str] = data.get("allowedProducerPaths", [])
        self.runtime_package_paths: List[str] = data.get("runtimePackagePaths", [])

    @property
    def is_baseline_pending(self) -> bool:
        return self.mode == "baseline-pending"


class Finding(NamedTuple):
    file: str
    line: int
    message: str

    def key(self, root: str) -> str:
        rel = os.path.relpath(self.file, root).replace("\\", "/")
        return f"{rel}:{self.line}"


def ls_files(root: str, *patterns: str) -> List[str]:
    """Return source files matching patterns; fall back to os.walk outside a git repo."""
    try:
        args = ["git", "-C", root, "ls-files", "--"] + list(patterns)
        res = subprocess.run(args, capture_output=True, text=True, timeout=60)
        if res.returncode == 0 and res.stdout.strip():
            files = []
            for p in res.stdout.splitlines():
                p = p.strip()
                if not p:
                    continue
                if any(seg in PRUNE_DIRS for seg in p.replace("\\", "/").split("/")):
                    continue
                files.append(os.path.join(root, p))
            return files
    except Exception:
        pass
    # Fallback: os.walk
    exts = tuple(pat.lstrip("*") for pat in patterns)
    out = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in PRUNE_DIRS]
        for fn in filenames:
            if any(fn.endswith(e) for e in exts):
                out.append(os.path.join(dirpath, fn))
    return out


def evaluate(
    findings: List[Finding],
    policy: Policy,
    root: str,
    gate_name: str,
    report_mode: bool = False,
) -> int:
    """Apply ratchet logic. Returns exit code (0 = pass, 1 = fail).

    baseline-pending: all findings are warnings; always exit 0.
    ratchet:
      - finding whose key is NOT in knownUnhandled  -> error (exit 1)
      - finding whose key IS in knownUnhandled      -> warning (exit 0)
      - knownUnhandled entry with no matching finding -> stale error (exit 1)
    """
    if report_mode or policy.is_baseline_pending:
        mode_tag = "baseline-pending" if policy.is_baseline_pending else "report"
        for f in findings:
            print(f"::warning title={gate_name}::[{mode_tag}] {f.key(root)} — {f.message}")
        if findings:
            print(
                f"\n{gate_name}: {len(findings)} finding(s). "
                "Suggested knownUnhandled entries (copy into policy, then flip mode to ratchet):"
            )
            for f in findings:
                print(f'  "{f.key(root)}"')
        else:
            print(f"{gate_name}: no findings.")
        return 0

    # ratchet mode: enforce
    keys = {f.key(root) for f in findings}
    known = set(policy.known_unhandled)
    exit_code = 0

    for f in findings:
        if f.key(root) in known:
            print(f"::warning title={gate_name}::known-unhandled {f.key(root)} — {f.message}")
        else:
            print(f"::error title={gate_name}::NEW {f.key(root)} — {f.message}")
            exit_code = 1

    for stale in sorted(known - keys):
        print(
            f"::error title={gate_name}::stale knownUnhandled entry {stale!r} — "
            "finding no longer exists; remove it from policy file."
        )
        exit_code = 1

    new_count = sum(1 for f in findings if f.key(root) not in known)
    if exit_code == 0:
        if findings:
            print(f"{gate_name}: OK ({len(findings)} known-unhandled).")
        else:
            print(f"{gate_name}: OK (no findings).")
    else:
        print(f"{gate_name}: FAIL ({new_count} new violation(s)).")
    return exit_code
