#!/usr/bin/env python3
"""gate-idempotent-consumer — every consumer uses the shared runtime.

No raw AIOKafkaConsumer / consumer.run() / kafka.consumer() calls outside the
runtime package paths declared in governance/idempotent-consumer-policy.json.

Policy: governance/idempotent-consumer-policy.json
  mode: baseline-pending  → warn + suggest baseline, exit 0
  mode: ratchet           → fail on new violations
  runtimePaths            → list of path prefixes that ARE the runtime (not violations)

Usage:
  gate_idempotent_consumer.py [root] [--report]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from event_gate_lib import GateResult, load_policy, read_lines, tracked_files

GATE_NAME = "gate-idempotent-consumer"

RAW_CONSUMER_RE = re.compile(
    r"""
    (
        AIOKafkaConsumer\s*\(           # from aiokafka
      | KafkaConsumer\s*\(             # from kafka-python
      | confluent_kafka.*Consumer\s*\( # from confluent_kafka
      | consumer\s*\.\s*run\s*\(       # consumer.run(
      | kafka\s*\.\s*consumer\s*\(     # kafka.consumer( — kafkajs
    )
    """,
    re.VERBOSE,
)

# Default runtime path segments — files under these paths ARE the runtime.
DEFAULT_RUNTIME_PATHS = {
    "event_consumer",
    "event_runtime",
    "kafka_runtime",
    "consumer_runtime",
}


def _load_runtime_paths(root: str) -> set[str]:
    path = os.path.join(root, "governance", "idempotent-consumer-policy.json")
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        extra = data.get("runtimePaths", [])
        if isinstance(extra, list):
            return DEFAULT_RUNTIME_PATHS | {p.lower() for p in extra}
    except Exception:
        pass
    return set(DEFAULT_RUNTIME_PATHS)


def _is_runtime_path(path: str, runtime_paths: set[str]) -> bool:
    parts = path.replace("\\", "/").lower().split("/")
    return any(rp in parts for rp in runtime_paths)


def scan(root: str) -> list[str]:
    runtime_paths = _load_runtime_paths(root)
    findings: list[str] = []
    for path in tracked_files(root, ".py", ".ts", ".tsx", ".js", ".mjs"):
        if _is_runtime_path(path, runtime_paths):
            continue
        for lineno, line in read_lines(path):
            if RAW_CONSUMER_RE.search(line):
                rel = os.path.relpath(path, root)
                findings.append(
                    f"{rel}:{lineno} — raw Kafka consumer call (use the shared consumer runtime)"
                )
    return findings


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", nargs="?", default=".")
    parser.add_argument("--report", action="store_true")
    args = parser.parse_args()

    root = os.path.abspath(args.root)
    policy = load_policy(root, GATE_NAME)
    result = GateResult(GATE_NAME, policy)

    for f in scan(root):
        result.add(f)

    return result.evaluate(report_only=args.report)


if __name__ == "__main__":
    sys.exit(main())
