#!/usr/bin/env python3
"""gate-outbox — no direct Kafka producer call outside the transactional-outbox relay.

Scans Python and TypeScript source files for direct Kafka producer patterns
(AIOKafkaProducer, KafkaProducer, producer.send, producer.produce) that are
NOT routed through the designated outbox relay module.

Policy: governance/outbox-policy.json
  mode: baseline-pending  → warn + suggest baseline, exit 0
  mode: ratchet           → fail on new violations

Usage:
  gate_outbox.py [root] [--report]
  --report  always exits 0 (use in CI to print findings without blocking)
"""
from __future__ import annotations

import argparse
import os
import re
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from event_gate_lib import GateResult, load_policy, read_lines, tracked_files

GATE_NAME = "gate-outbox"

# Patterns that indicate a direct Kafka producer (not through the outbox relay).
DIRECT_PRODUCER_RE = re.compile(
    r"""
    (
        AIOKafkaProducer\s*\(            # from aiokafka
      | KafkaProducer\s*\(              # from kafka-python
      | confluent_kafka.*Producer\s*\(  # from confluent_kafka
      | new\s+Kafka\s*\(                # kafkajs Kafka constructor
      | producer\s*\.\s*send\s*\(       # producer.send(topic,
      | producer\s*\.\s*produce\s*\(    # producer.produce(topic,
    )
    """,
    re.VERBOSE,
)

# Paths that ARE the outbox relay implementation — not violations.
OUTBOX_RELAY_PATHS = {
    "outbox",
    "event_relay",
    "event_bus",
    "kafka_relay",
}


def _is_relay_path(path: str) -> bool:
    """True if the file is part of the outbox relay itself."""
    parts = path.replace("\\", "/").lower().split("/")
    return any(rel in parts for rel in OUTBOX_RELAY_PATHS)


def scan(root: str) -> list[str]:
    """Return a list of finding strings."""
    findings: list[str] = []
    for path in tracked_files(root, ".py", ".ts", ".tsx", ".js", ".mjs"):
        if _is_relay_path(path):
            continue
        for lineno, line in read_lines(path):
            if DIRECT_PRODUCER_RE.search(line):
                rel = os.path.relpath(path, root)
                findings.append(f"{rel}:{lineno} — direct Kafka producer call (route through outbox relay)")
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
