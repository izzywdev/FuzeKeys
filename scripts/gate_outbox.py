#!/usr/bin/env python3
"""gate-outbox — No direct Kafka producer calls outside the transactional-outbox relay.

Patterns that signal a direct producer call:
  Python:  AIOKafkaProducer(  KafkaProducer(  producer.send(  producer.produce(
  TS/JS:   kafka.producer(  producer.send(  new KafkaProducer(

Allowed locations are declared in governance/outbox-policy.json (allowedProducerPaths).

Modes:
  baseline-pending  full scan, warning annotations, exit 0
  ratchet           new violations exit 1; knownUnhandled entries warn

Usage:
  gate_outbox.py [root]           enforcing
  gate_outbox.py [root] --report  full report, always exit 0

Policy: governance/outbox-policy.json
"""
from __future__ import annotations
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from event_gate_lib import Policy, Finding, evaluate, ls_files

GATE = "gate-outbox"
POLICY_REL = os.path.join("governance", "outbox-policy.json")

_PY_PATTERNS = [
    re.compile(r"\bAIOKafkaProducer\s*\("),
    re.compile(r"\bKafkaProducer\s*\("),
    re.compile(r"\bproducer\s*\.\s*send\s*\("),
    re.compile(r"\bproducer\s*\.\s*produce\s*\("),
]
_TS_PATTERNS = [
    re.compile(r"\bkafka\s*\.\s*producer\s*\("),
    re.compile(r"\bproducer\s*\.\s*send\s*\("),
    re.compile(r"\bnew\s+KafkaProducer\s*\("),
]


def _patterns_for(path: str) -> list:
    if path.endswith((".ts", ".tsx", ".js", ".mjs", ".cjs")):
        return _TS_PATTERNS
    if path.endswith(".py"):
        return _PY_PATTERNS
    return []


def _in_allowed(path: str, root: str, allowed: list) -> bool:
    rel = os.path.relpath(path, root).replace("\\", "/")
    for ap in allowed:
        ap = ap.replace("\\", "/").rstrip("/")
        if rel == ap or rel.startswith(ap + "/"):
            return True
    return False


def scan(root: str, policy: Policy) -> list:
    findings = []
    source_files = ls_files(root, "*.py", "*.ts", "*.tsx", "*.js", "*.mjs", "*.cjs")
    for path in source_files:
        if _in_allowed(path, root, policy.allowed_producer_paths):
            continue
        pats = _patterns_for(path)
        if not pats:
            continue
        try:
            with open(path, encoding="utf-8", errors="replace") as f:
                for lineno, line in enumerate(f, 1):
                    for pat in pats:
                        if pat.search(line):
                            findings.append(Finding(
                                file=path,
                                line=lineno,
                                message=(
                                    "direct Kafka producer call outside outbox relay: "
                                    + line.strip()[:80]
                                ),
                            ))
                            break
        except OSError:
            continue
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
