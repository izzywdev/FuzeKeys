#!/usr/bin/env python3
"""gate-idempotent-consumer — every consumer uses the shared runtime.

Raw Kafka consumer instantiation (AIOKafkaConsumer, KafkaConsumer, consumer.run())
outside the shared runtime package bypasses inbox dedupe, version guards, and the
DLQ, making the consumer non-idempotent (governance/data-consistency-standard.md §4).

Policy file: governance/idempotent-consumer-policy.json
  mode           "baseline-pending" (default) | "ratchet"
  runtimePaths   repo-relative path prefixes of the shared consumer runtime package
                 (these files ARE the runtime — they may instantiate consumers directly)
  knownUnhandled shrink-only list of pre-existing "relpath:line — …" strings

Usage: gate_idempotent_consumer.py [root] [--report]
  --report  print every finding + suggested baseline; always exits 0
"""
from __future__ import annotations

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from event_gate_lib import apply_ratchet, git_tracked_py_files, load_policy  # noqa: E402

GATE_NAME = "gate-idempotent-consumer"
GATE_KEY = "idempotent-consumer"

# Patterns that flag a raw consumer instantiation.
_CONSUMER_RES = [
    re.compile(r"\bAIOKafkaConsumer\s*\("),
    re.compile(r"\bKafkaConsumer\s*\("),
    re.compile(r"\bconsumer\.run\s*\("),
    re.compile(r"\bconsumer\.start\s*\("),
    re.compile(r"from\s+aiokafka\b.*\bAIOKafkaConsumer\b"),
    re.compile(r"from\s+kafka\b.*\bKafkaConsumer\b"),
    re.compile(r"\baiokafka\.AIOKafkaConsumer\b"),
]


def _in_runtime(rel: str, runtime_paths: list[str]) -> bool:
    norm = rel.replace("\\", "/")
    for rp in (runtime_paths or []):
        rp_norm = rp.strip("/").replace("\\", "/")
        if norm == rp_norm or norm.startswith(rp_norm + "/"):
            return True
    return False


def find_violations(root: str, policy: dict) -> list[str]:
    """Return 'relpath:lineno — reason' strings for each raw consumer instantiation."""
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
            for pat in _CONSUMER_RES:
                if pat.search(line):
                    violations.append(
                        f"{rel}:{lineno} — raw Kafka consumer outside shared runtime"
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
