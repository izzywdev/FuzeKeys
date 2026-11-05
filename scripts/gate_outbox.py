#!/usr/bin/env python3
"""gate-outbox — forbid direct Kafka producer calls outside the transactional-outbox relay.

WHY THIS EXISTS. Publishing a domain event directly from a request handler breaks
atomicity: the write to the database and the write to Kafka are two separate operations.
A crash between them produces a half-committed state — the database row exists but the
event is never published, or the event fires but the row is rolled back.  The
transactional outbox pattern fixes this: the service writes an outbox row in the SAME
transaction as the business row, and a separate relay process publishes it. The gate
enforces that no code outside the relay directly instantiates or calls a Kafka producer.

WHAT IS FLAGGED. Any line in a tracked Python or TypeScript/JavaScript file that
contains a direct producer instantiation or send call:
  Python  — AIOKafkaProducer(  KafkaProducer(  confluent_kafka.Producer(
            producer.send(   producer.produce(
  TS/JS   — new Kafka(   createProducer(   .producer().send(

WHAT IS EXEMPT. Files whose path contains any of: outbox, event_relay, event_bus,
kafka_relay.  The relay itself legitimately instantiates producers; every other caller
must go through it.  Test files are NOT auto-exempt — a test that creates a real
producer outside the relay is evidence the relay is not being used in that code path.

RATCHET (governance/outbox-policy.json).  A missing policy file is treated as
{"mode": "fail", "knownUnhandled": []}.  Deleting the file must never silence this gate.
mode=warn  → report all hits, exit 0 (initial rollout posture).
mode=fail  → any hit not in knownUnhandled exits 1 immediately.

A knownUnhandled entry is "rel/path.py:line" (or bare "rel/path.py" for the whole file).
A hit whose line number has moved since the entry was written will re-violate — ratchets
are not a free pass, they are a time-bound remediation agreement.

Usage:
    python scripts/gate_outbox.py [root] [--report]
    --report  print all hits and suggest ratchet entries; always exits 0
Exit codes: 0 = clean (or report mode)   1 = violation   2 = usage error
"""
from __future__ import annotations

import os
import re
import sys

# Bring in the shared library.  When run from repo root the scripts/ dir must be on
# the path; when invoked directly it already is because __file__ is in scripts/.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import event_gate_lib  # noqa: E402

POLICY_REL = os.path.join("governance", "outbox-policy.json")

PRODUCER_PATTERNS: list[re.Pattern] = [
    re.compile(r"\bAIOKafkaProducer\s*\("),
    re.compile(r"\bKafkaProducer\s*\("),
    re.compile(r"\bconfluent_kafka\s*\.\s*Producer\s*\("),
    re.compile(r"\bproducer\s*\.\s*send\s*\("),
    re.compile(r"\bproducer\s*\.\s*produce\s*\("),
    re.compile(r"\bnew\s+Kafka\s*\("),
    re.compile(r"\bcreateProducer\s*\("),
]

SKIP_PATH_RE = re.compile(r"/(outbox|event_relay|event_bus|kafka_relay)/", re.IGNORECASE)

SOURCE_EXTENSIONS = (".py", ".ts", ".tsx", ".js", ".jsx", ".mjs")


def run(root: str, report_only: bool) -> int:
    files = event_gate_lib.candidate_files(root, extensions=SOURCE_EXTENSIONS)
    policy = event_gate_lib.load_policy(root, POLICY_REL)
    hits = event_gate_lib.scan_lines(files, PRODUCER_PATTERNS, SKIP_PATH_RE)
    violations, suppressed = event_gate_lib.apply_ratchet(hits, root, policy)

    mode = policy.get("mode", "fail")

    if report_only:
        print(f"gate-outbox: --report  mode={mode}  files_scanned={len(files)}")
        if not hits:
            print("gate-outbox: no direct producer calls found")
            return 0
        print(f"\ngate-outbox: {len(hits)} hit(s) ({len(violations)} violation(s), {len(suppressed)} suppressed)\n")
        for path, lineno, line in hits:
            r = event_gate_lib.rel(root, path)
            tag = "SUPPRESSED" if (path, lineno, line) in suppressed else "VIOLATION"
            print(f"  [{tag}] {r}:{lineno}  {line.strip()}")
        if violations:
            print("\nSuggested knownUnhandled entries for governance/outbox-policy.json:")
            for entry in event_gate_lib.suggest_ratchet(violations, root):
                print(f'    "{entry}"')
        return 0

    if suppressed:
        print(f"gate-outbox: {len(suppressed)} hit(s) suppressed by knownUnhandled")
        for path, lineno, _ in suppressed:
            print(f"  ~ {event_gate_lib.rel(root, path)}:{lineno}")

    if violations:
        print(f"\ngate-outbox: {len(violations)} violation(s)\n")
        for path, lineno, line in violations:
            print(f"  ✗ {event_gate_lib.rel(root, path)}:{lineno}  {line.strip()}")
        print(
            "\nAll domain-event publishing must go through the transactional-outbox relay."
            "\nSee governance/data-consistency-standard.md §3."
            "\nTo ratchet an existing site, add it to governance/outbox-policy.json"
            "\nunder knownUnhandled with a remediation date, and set mode=fail."
        )
        return 1

    print(f"gate-outbox: OK  (files_scanned={len(files)}, mode={mode})")
    return 0


def main(argv: list[str]) -> int:
    args = [a for a in argv[1:] if not a.startswith("--")]
    flags = {a for a in argv[1:] if a.startswith("--")}
    known_flags = {"--report"}
    unknown = flags - known_flags
    if unknown:
        print(f"gate-outbox: unknown flag(s) {' '.join(sorted(unknown))}", file=sys.stderr)
        return 2
    root = args[0] if args else "."
    report_only = "--report" in flags
    return run(root, report_only)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
