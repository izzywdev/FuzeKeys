#!/usr/bin/env python3
"""gate-idempotent-consumer — forbid raw Kafka consumer calls outside the shared consumer runtime.

WHY THIS EXISTS.  A raw Kafka consumer has no built-in deduplication, inbox tracking,
version guarding, or dead-letter queue handling.  Every service that wires one directly
must reimplement all of that — and historically none of them did.  The shared consumer
runtime bundles idempotency (inbox table), version-guarded dispatch, and automatic DLQ
routing.  This gate enforces that every consumer is built on the shared runtime; no
service may call consumer.run()/AIOKafkaConsumer()/etc. directly.

WHAT IS FLAGGED. Any line in a tracked Python or TypeScript/JavaScript file that
creates or starts a raw consumer:
  Python  — AIOKafkaConsumer(   KafkaConsumer(   confluent_kafka.Consumer(
            consumer.run(
  TS/JS   — kafka.consumer(   consumer.run(

WHAT IS EXEMPT.  File paths declared in the policy's `runtimePaths` list.  The shared
consumer runtime itself legitimately instantiates consumers; all other call sites must go
through it.  Add the runtime module path(s) to governance/idempotent-consumer-policy.json.

RATCHET (governance/idempotent-consumer-policy.json).  Missing file →
{"mode": "fail", "runtimePaths": [], "knownUnhandled": []}.
mode=warn  → report all hits, exit 0.
mode=fail  → any hit not in knownUnhandled exits 1.

Usage:
    python scripts/gate_idempotent_consumer.py [root] [--report]
Exit codes: 0 = clean (or report mode)   1 = violation   2 = usage error
"""
from __future__ import annotations

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import event_gate_lib  # noqa: E402

POLICY_REL = os.path.join("governance", "idempotent-consumer-policy.json")

CONSUMER_PATTERNS: list[re.Pattern] = [
    re.compile(r"\bAIOKafkaConsumer\s*\("),
    re.compile(r"\bKafkaConsumer\s*\("),
    re.compile(r"\bconfluent_kafka\s*\.\s*Consumer\s*\("),
    re.compile(r"\bconsumer\s*\.\s*run\s*\("),
    re.compile(r"\bkafka\s*\.\s*consumer\s*\("),
]

SOURCE_EXTENSIONS = (".py", ".ts", ".tsx", ".js", ".jsx", ".mjs")


def _build_skip_re(runtime_paths: list[str]) -> re.Pattern | None:
    if not runtime_paths:
        return None
    escaped = [re.escape(p.replace("\\", "/").strip("/")) for p in runtime_paths if p.strip()]
    if not escaped:
        return None
    return re.compile("(" + "|".join(escaped) + ")", re.IGNORECASE)


def run(root: str, report_only: bool) -> int:
    files = event_gate_lib.candidate_files(root, extensions=SOURCE_EXTENSIONS)
    policy = event_gate_lib.load_policy(root, POLICY_REL)
    runtime_paths: list[str] = policy.get("runtimePaths", [])
    skip_re = _build_skip_re(runtime_paths)

    hits = event_gate_lib.scan_lines(files, CONSUMER_PATTERNS, skip_re)
    violations, suppressed = event_gate_lib.apply_ratchet(hits, root, policy)
    mode = policy.get("mode", "fail")

    if report_only:
        print(f"gate-idempotent-consumer: --report  mode={mode}  files_scanned={len(files)}")
        if not hits:
            print("gate-idempotent-consumer: no raw consumer calls found")
            return 0
        print(f"\ngate-idempotent-consumer: {len(hits)} hit(s) ({len(violations)} violation(s), {len(suppressed)} suppressed)\n")
        for path, lineno, line in hits:
            r = event_gate_lib.rel(root, path)
            tag = "SUPPRESSED" if (path, lineno, line) in suppressed else "VIOLATION"
            print(f"  [{tag}] {r}:{lineno}  {line.strip()}")
        if violations:
            print("\nSuggested knownUnhandled entries for governance/idempotent-consumer-policy.json:")
            for entry in event_gate_lib.suggest_ratchet(violations, root):
                print(f'    "{entry}"')
        return 0

    if suppressed:
        print(f"gate-idempotent-consumer: {len(suppressed)} hit(s) suppressed (runtimePaths or knownUnhandled)")
        for path, lineno, _ in suppressed:
            print(f"  ~ {event_gate_lib.rel(root, path)}:{lineno}")

    if violations:
        print(f"\ngate-idempotent-consumer: {len(violations)} violation(s)\n")
        for path, lineno, line in violations:
            print(f"  ✗ {event_gate_lib.rel(root, path)}:{lineno}  {line.strip()}")
        print(
            "\nAll event consumers must use the shared consumer runtime."
            "\nSee governance/data-consistency-standard.md §4."
            "\nTo exempt the runtime module itself, add its path to runtimePaths in"
            "\ngovernance/idempotent-consumer-policy.json."
            "\nTo ratchet an existing site, add it to knownUnhandled with a remediation date."
        )
        return 1

    print(f"gate-idempotent-consumer: OK  (files_scanned={len(files)}, mode={mode})")
    return 0


def main(argv: list[str]) -> int:
    args = [a for a in argv[1:] if not a.startswith("--")]
    flags = {a for a in argv[1:] if a.startswith("--")}
    known_flags = {"--report"}
    unknown = flags - known_flags
    if unknown:
        print(f"gate-idempotent-consumer: unknown flag(s) {' '.join(sorted(unknown))}", file=sys.stderr)
        return 2
    root = args[0] if args else "."
    report_only = "--report" in flags
    return run(root, report_only)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
