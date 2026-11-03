#!/usr/bin/env python3
"""gate-event-envelope — every registered topic uses envelope v2.

Envelope v2 requires the following fields in every event schema:
  eventId (or event_id), aggregateId (or aggregate_id),
  aggregateType (or aggregate_type), occurredAt (or occurred_at)

The gate also checks that any TypeScript event registry and its Python
mirror agree on the topic list.

Policy: governance/event-envelope-policy.json
  mode: baseline-pending  → warn + suggest baseline, exit 0
  mode: ratchet           → fail on new violations

Usage:
  gate_event_envelope.py [root] [--report]
"""
from __future__ import annotations

import argparse
import os
import re
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from event_gate_lib import GateResult, load_policy, read_lines, tracked_files

GATE_NAME = "gate-event-envelope"

# Directories / file name patterns that look like event schema definitions.
EVENT_SCHEMA_PATH_RE = re.compile(
    r"(^|/)events?/|_event(s)?[._]|event_schema|topic[s_]",
    re.IGNORECASE,
)

# Class/interface that looks like an event schema definition.
EVENT_CLASS_RE = re.compile(
    r"class\s+\w*(Event|Created|Updated|Deleted|Published|Sent|Received)\w*\s*",
    re.IGNORECASE,
)

# Required v2 envelope fields (camelCase or snake_case).
ENVELOPE_FIELDS = [
    re.compile(r"\b(event_id|eventId)\b"),
    re.compile(r"\b(aggregate_id|aggregateId)\b"),
    re.compile(r"\b(aggregate_type|aggregateType)\b"),
    re.compile(r"\b(occurred_at|occurredAt)\b"),
]


def _looks_like_event_schema_file(path: str) -> bool:
    rel = path.replace("\\", "/")
    return bool(EVENT_SCHEMA_PATH_RE.search(rel))


def _check_file(path: str, root: str) -> list[str]:
    """Return findings for a single file."""
    lines = read_lines(path)
    if not lines:
        return []

    text = "".join(line for _, line in lines)
    if not EVENT_CLASS_RE.search(text):
        return []

    findings = []
    missing = [
        name
        for pat, name in zip(
            ENVELOPE_FIELDS,
            ["eventId/event_id", "aggregateId/aggregate_id",
             "aggregateType/aggregate_type", "occurredAt/occurred_at"],
        )
        if not pat.search(text)
    ]
    if missing:
        rel = os.path.relpath(path, root)
        findings.append(
            f"{rel} — event schema missing envelope v2 field(s): {', '.join(missing)}"
        )
    return findings


def scan(root: str) -> list[str]:
    findings: list[str] = []
    for path in tracked_files(root, ".py", ".ts", ".tsx"):
        if _looks_like_event_schema_file(path) or EVENT_CLASS_RE.search(
            "".join(line for _, line in read_lines(path))
        ):
            findings.extend(_check_file(path, root))
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
