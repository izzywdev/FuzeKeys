#!/usr/bin/env python3
"""gate-idempotent-consumer — data-consistency standard §4.

No raw Kafka consumer construction outside the shared runtime package.

Scans Python / TypeScript / JavaScript source for direct consumer
instantiation patterns. Paths listed in idempotent-consumer-policy.json
runtimePaths are exempt (the runtime package itself may use the raw API).

Operates as a RATCHET:
  baseline-pending (seeded default) — scan, warn, suggest baseline, exit 0.
  ratchet                           — new violations fail; known ones warn.

Usage:
  gate_idempotent_consumer.py [root]            enforce
  gate_idempotent_consumer.py [root] --report   report-only (always exit 0)
"""
from __future__ import annotations

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
from event_gate_lib import load_policy, run_ratchet, scan_for_patterns  # noqa: E402

# Patterns that indicate a raw Kafka consumer is being instantiated outside
# the approved runtime package.
CONSUMER_PATTERNS = [
    r"AIOKafkaConsumer\s*\(",
    r"KafkaConsumer\s*\(",
    r"aiokafka\.AIOKafkaConsumer\s*\(",
    r"new\s+Kafka\s*\(.*\)\s*\.consumer\s*\(",
    r"\.consumer\s*\(\s*\{",
]


def main() -> int:
    args = sys.argv[1:]
    report_only = "--report" in args
    pos = [a for a in args if not a.startswith("-")]
    root = pos[0] if pos else "."

    policy = load_policy(root, "idempotent-consumer")
    runtime_paths: list[str] = policy.get("runtimePaths", []) or []

    findings = scan_for_patterns(root, CONSUMER_PATTERNS, exclude_paths=runtime_paths)

    if report_only:
        if findings:
            print(f"gate-idempotent-consumer (report): {len(findings)} finding(s)")
            for relpath, lineno, line in findings:
                print(f"  {relpath}:{lineno}: {line.strip()}")
        else:
            print("gate-idempotent-consumer (report): no findings")
        return 0

    return run_ratchet(findings, policy, "gate-idempotent-consumer")


if __name__ == "__main__":
    sys.exit(main())
