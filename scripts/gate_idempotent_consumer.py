#!/usr/bin/env python3
"""gate-idempotent-consumer — No raw Kafka consumer instantiation outside the runtime.

Patterns that signal a raw consumer:
  Python:  AIOKafkaConsumer(  KafkaConsumer(
  TS/JS:   kafka.consumer(  consumer.run( (when adjacent to kafka.consumer)

consumer.run( in Python is only flagged when the file also imports aiokafka or kafka,
to avoid false positives from non-Kafka code.

Allowed locations are declared in governance/idempotent-consumer-policy.json (runtimePackagePaths).

Modes:
  baseline-pending  full scan, warning annotations, exit 0
  ratchet           new violations exit 1; knownUnhandled entries warn

Usage:
  gate_idempotent_consumer.py [root]           enforcing
  gate_idempotent_consumer.py [root] --report  full report, always exit 0

Policy: governance/idempotent-consumer-policy.json
"""
from __future__ import annotations
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from event_gate_lib import Policy, Finding, evaluate, ls_files

GATE = "gate-idempotent-consumer"
POLICY_REL = os.path.join("governance", "idempotent-consumer-policy.json")

_PY_DIRECT = [
    re.compile(r"\bAIOKafkaConsumer\s*\("),
    re.compile(r"\bKafkaConsumer\s*\("),
]
_PY_CONSUMER_RUN = re.compile(r"\bconsumer\s*\.\s*run\s*\(")
_PY_KAFKA_IMPORT = re.compile(r"(?:from|import)\s+(?:aiokafka|kafka)\b")

_TS_PATTERNS = [
    re.compile(r"\bkafka\s*\.\s*consumer\s*\("),
    re.compile(r"\bconsumer\s*\.\s*run\s*\("),
]


def _in_allowed(path: str, root: str, allowed: list) -> bool:
    rel = os.path.relpath(path, root).replace("\\", "/")
    for ap in allowed:
        ap = ap.replace("\\", "/").rstrip("/")
        if rel == ap or rel.startswith(ap + "/"):
            return True
    return False


def _scan_py(path: str) -> list:
    hits = []
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
        has_kafka = any(_PY_KAFKA_IMPORT.search(ln) for ln in lines)
        for i, line in enumerate(lines, 1):
            matched = False
            for pat in _PY_DIRECT:
                if pat.search(line):
                    hits.append((i, line.strip()))
                    matched = True
                    break
            if not matched and has_kafka and _PY_CONSUMER_RUN.search(line):
                hits.append((i, line.strip()))
    except OSError:
        pass
    return hits


def _scan_ts(path: str) -> list:
    hits = []
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            for i, line in enumerate(f, 1):
                for pat in _TS_PATTERNS:
                    if pat.search(line):
                        hits.append((i, line.strip()))
                        break
    except OSError:
        pass
    return hits


def scan(root: str, policy: Policy) -> list:
    findings = []
    source_files = ls_files(root, "*.py", "*.ts", "*.tsx", "*.js", "*.mjs", "*.cjs")
    for path in source_files:
        if _in_allowed(path, root, policy.runtime_package_paths):
            continue
        if path.endswith(".py"):
            hits = _scan_py(path)
        elif path.endswith((".ts", ".tsx", ".js", ".mjs", ".cjs")):
            hits = _scan_ts(path)
        else:
            continue
        for lineno, snippet in hits:
            findings.append(Finding(
                file=path,
                line=lineno,
                message=f"raw Kafka consumer outside runtime: {snippet[:80]}",
            ))
    return findings


def main(argv=None):
    args = sys.argv[1:] if argv is None else argv
    report_mode = "--report" in args
    args = [a for a in args if a != "--report"]
    root = os.path.abspath(args[0] if args else ".")

    policy_path = os.path.join(root, POLICY_REL)
    policy = Policy(policy_path if os.path.isfile(policy_path) else None)
    findings = scan(root, policy)
    return evaluate(findings, policy, root, GATE, report_mode)


if __name__ == "__main__":
    sys.exit(main())
