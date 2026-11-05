#!/usr/bin/env python3
"""gate-outbox — data-consistency standard §3.

No direct Kafka producer call outside the transactional-outbox relay.

Scans Python / TypeScript / JavaScript source for raw producer-instantiation
patterns. Paths listed in outbox-policy.json runtimePaths are exempt (the
relay implementation itself may use the raw API).

Operates as a RATCHET:
  baseline-pending (seeded default) — scan, warn, suggest baseline, exit 0.
  ratchet                           — new violations fail; known ones warn.

Usage:
  gate_outbox.py [root]            enforce
  gate_outbox.py [root] --report   report-only (always exit 0)
"""
from __future__ import annotations

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
from event_gate_lib import load_policy, run_ratchet, scan_for_patterns  # noqa: E402

# Patterns that indicate a raw Kafka producer is being instantiated or used
# directly rather than through the outbox relay.
PRODUCER_PATTERNS = [
    r"AIOKafkaProducer\s*\(",
    r"KafkaProducer\s*\(",
    r"confluent_kafka\.Producer\s*\(",
    r"new\s+Kafka\s*\(.*\)\s*\.producer\s*\(",
    r"\.producer\s*\(\s*\)",
]


def main() -> int:
    args = sys.argv[1:]
    report_only = "--report" in args
    pos = [a for a in args if not a.startswith("-")]
    root = pos[0] if pos else "."

    policy = load_policy(root, "outbox")
    runtime_paths: list[str] = policy.get("runtimePaths", []) or []

    findings = scan_for_patterns(root, PRODUCER_PATTERNS, exclude_paths=runtime_paths)

    if report_only:
        if findings:
            print(f"gate-outbox (report): {len(findings)} finding(s)")
            for relpath, lineno, line in findings:
                print(f"  {relpath}:{lineno}: {line.strip()}")
        else:
            print("gate-outbox (report): no findings")
        return 0

    return run_ratchet(findings, policy, "gate-outbox")


if __name__ == "__main__":
    sys.exit(main())
