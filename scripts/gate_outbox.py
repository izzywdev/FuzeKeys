#!/usr/bin/env python3
"""gate-outbox — no direct Kafka producer call outside the transactional-outbox relay.

Every domain-event publish must go through the transactional outbox in the same
transaction as the write (governance/data-consistency-standard.md §3).  A direct
KafkaProducer / AIOKafkaProducer / producer.send() call bypasses that guarantee.

Policy file: governance/outbox-policy.json
  mode           "baseline-pending" (default) | "ratchet"
  runtimePaths   repo-relative path prefixes of the outbox relay implementation
                 (these files ARE the relay — they may call the producer directly)
  knownUnhandled shrink-only list of pre-existing "relpath:line — …" strings

Usage: gate_outbox.py [root] [--report]
  --report  print every finding + suggested baseline; always exits 0
"""
from __future__ import annotations

import os
import re
import sys

# Allow `python scripts/gate_outbox.py` from the repo root AND loading via
# importlib from scripts/__tests__/ — either way, scripts/ is on the path.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from event_gate_lib import apply_ratchet, git_tracked_py_files, load_policy  # noqa: E402

GATE_NAME = "gate-outbox"
GATE_KEY = "outbox"

# Patterns that flag a direct Kafka producer call (violation when outside relay).
_PRODUCER_RES = [
    re.compile(r"\bAIOKafkaProducer\s*\("),
    re.compile(r"\bKafkaProducer\s*\("),
    re.compile(r"\bproducer\.send\s*\("),
    re.compile(r"\bproducer\.produce\s*\("),
    re.compile(r"from\s+aiokafka\b.*\bAIOKafkaProducer\b"),
    re.compile(r"from\s+kafka\b.*\bKafkaProducer\b"),
    re.compile(r"\baiokafka\.AIOKafkaProducer\b"),
]


def _in_runtime(rel: str, runtime_paths: list[str]) -> bool:
    norm = rel.replace("\\", "/")
    for rp in (runtime_paths or []):
        rp_norm = rp.strip("/").replace("\\", "/")
        if norm == rp_norm or norm.startswith(rp_norm + "/"):
            return True
    return False


def find_violations(root: str, policy: dict) -> list[str]:
    """Return 'relpath:lineno — reason' strings for each direct producer call."""
    runtime_paths: list[str] = policy.get("runtimePaths", []) or []
    violations: list[str] = []
    for path in git_tracked_py_files(root):
        rel = os.path.relpath(path, root).replace("\\", "/")
        if _in_runtime(rel, runtime_paths):
            continue
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as fh:
                lines = fh.readlines()
        except OSError:
            continue
        for lineno, line in enumerate(lines, 1):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            for pat in _PRODUCER_RES:
                if pat.search(line):
                    violations.append(
                        f"{rel}:{lineno} — direct Kafka producer call outside outbox relay"
                    )
                    break
    return violations


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    root = "."
    report_mode = False
    for a in args:
        if a == "--report":
            report_mode = True
        elif not a.startswith("-"):
            root = a
    root = os.path.abspath(root)
    policy = load_policy(root, GATE_KEY)
    violations = find_violations(root, policy)
    return apply_ratchet(violations, policy, GATE_NAME, report_mode)


if __name__ == "__main__":
    sys.exit(main())
