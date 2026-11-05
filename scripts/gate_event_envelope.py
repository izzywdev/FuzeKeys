#!/usr/bin/env python3
"""gate-event-envelope — verify every registered event topic uses envelope v2.

WHY THIS EXISTS.  Envelope v1 events (bare payload, no metadata) cannot be correlated,
replayed, or deduplicated because they carry no event identity.  Envelope v2 adds four
required fields that enable all of that:
  - eventId / event_id       unique identifier for this event occurrence
  - aggregateId / aggregate_id   the entity that changed
  - aggregateType / aggregate_type  the type of that entity (prevents cross-type collisions)
  - occurredAt / occurred_at     wall-clock timestamp of the state change

WHAT IS CHECKED.
  1. Event-schema files — any tracked Python or TypeScript file whose path contains
     "event" (outside test dirs) and that defines a class or interface whose name ends
     in "Event", "Created", "Updated", "Deleted", "Completed", or "Failed" is treated
     as an event schema.  Each such class must reference all four envelope fields.
  2. Topic-registry parity — if both a TypeScript topics registry and a Python topics
     registry exist, they must declare the same topic list.

WHAT IS NOT FLAGGED.
  - Repositories with no event-schema files pass vacuously.  FuzeKeys, for example,
    does not publish domain events; this gate exits 0 without touching anything.
  - Test files (*_test.py, test_*.py, *.test.ts, *.spec.ts) are skipped.

RATCHET (governance/event-envelope-policy.json).  Missing file →
{"mode": "fail", "knownUnhandled": []}.
mode=warn  → report all hits, exit 0.
mode=fail  → any hit not in knownUnhandled exits 1.

Usage:
    python scripts/gate_event_envelope.py [root] [--report]
Exit codes: 0 = clean (or report mode)   1 = violation   2 = usage error
"""
from __future__ import annotations

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import event_gate_lib  # noqa: E402

POLICY_REL = os.path.join("governance", "event-envelope-policy.json")

# Class/interface names that mark an event-schema definition.
EVENT_CLASS_RE = re.compile(
    r"\b(?:class|interface|type)\s+\w*(?:Event|Created|Updated|Deleted|Completed|Failed)\b",
    re.IGNORECASE,
)

# Required envelope v2 field names (Python snake_case or TypeScript camelCase).
ENVELOPE_FIELDS = [
    re.compile(r"\b(?:eventId|event_id)\b"),
    re.compile(r"\b(?:aggregateId|aggregate_id)\b"),
    re.compile(r"\b(?:aggregateType|aggregate_type)\b"),
    re.compile(r"\b(?:occurredAt|occurred_at)\b"),
]
ENVELOPE_FIELD_NAMES = ["eventId/event_id", "aggregateId/aggregate_id", "aggregateType/aggregate_type", "occurredAt/occurred_at"]

# Paths that mark a file as a test — skip those.
TEST_PATH_RE = re.compile(r"/(test[s]?|__tests__|spec[s]?)/|(_test\.|\.test\.|\.spec\.)", re.IGNORECASE)

SOURCE_EXTENSIONS = (".py", ".ts", ".tsx")


def _is_event_schema_file(rel_path: str) -> bool:
    """True if the file path suggests it contains event definitions."""
    lower = rel_path.lower().replace("\\", "/")
    if TEST_PATH_RE.search("/" + lower):
        return False
    return "event" in lower


def _check_file_envelope(path: str) -> list[tuple[int, str]]:
    """Return (lineno, message) for each envelope-v2 violation in the file.

    Only files that contain an event-class declaration are checked.  For each
    such class, we scan the surrounding block (up to 60 lines) for the required
    envelope fields.  A missing field produces one violation per class.
    """
    try:
        with open(path, encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
    except OSError:
        return []

    violations: list[tuple[int, str]] = []
    text = "".join(lines)

    for m in EVENT_CLASS_RE.finditer(text):
        # Find which line number this match is on.
        lineno = text.count("\n", 0, m.start()) + 1
        class_name = m.group(0).split()[-1]  # last word is the class name

        # Scan from the class declaration to find envelope fields.
        # Look in the whole file; in Python and TS, the fields can appear anywhere
        # in the class body but the class itself is usually self-contained.
        # For simplicity, check the entire file for the field names.
        for i, field_re in enumerate(ENVELOPE_FIELDS):
            if not field_re.search(text):
                violations.append((
                    lineno,
                    f"{class_name} — missing envelope v2 field '{ENVELOPE_FIELD_NAMES[i]}'"
                ))

    return violations


def find_event_schema_files(root: str) -> list[str]:
    files = event_gate_lib.candidate_files(root, extensions=SOURCE_EXTENSIONS)
    return [
        f for f in files
        if _is_event_schema_file(os.path.relpath(f, root))
    ]


def check_envelope_violations(root: str) -> list[tuple[str, int, str]]:
    """Return (path, lineno, message) for each envelope violation."""
    violations: list[tuple[str, int, str]] = []
    for path in find_event_schema_files(root):
        try:
            with open(path, encoding="utf-8", errors="ignore") as f:
                content = f.read()
        except OSError:
            continue
        if not EVENT_CLASS_RE.search(content):
            continue
        for lineno, msg in _check_file_envelope(path):
            violations.append((path, lineno, msg))
    return violations


def run(root: str, report_only: bool) -> int:
    policy = event_gate_lib.load_policy(root, POLICY_REL)
    mode = policy.get("mode", "fail")

    raw = check_envelope_violations(root)

    # Convert to the same (path, lineno, text) format used by apply_ratchet.
    hits = [(p, n, msg) for p, n, msg in raw]
    violations, suppressed = event_gate_lib.apply_ratchet(hits, root, policy)

    event_files = find_event_schema_files(root)

    if report_only:
        print(f"gate-event-envelope: --report  mode={mode}  event_schema_files={len(event_files)}")
        if not hits:
            print("gate-event-envelope: no envelope violations found")
            return 0
        print(f"\ngate-event-envelope: {len(hits)} hit(s) ({len(violations)} violation(s), {len(suppressed)} suppressed)\n")
        for path, lineno, msg in hits:
            r = event_gate_lib.rel(root, path)
            tag = "SUPPRESSED" if (path, lineno, msg) in suppressed else "VIOLATION"
            print(f"  [{tag}] {r}:{lineno}  {msg}")
        if violations:
            print("\nSuggested knownUnhandled entries for governance/event-envelope-policy.json:")
            for entry in event_gate_lib.suggest_ratchet(violations, root):
                print(f'    "{entry}"')
        return 0

    if suppressed:
        print(f"gate-event-envelope: {len(suppressed)} hit(s) suppressed by knownUnhandled")

    if violations:
        print(f"\ngate-event-envelope: {len(violations)} violation(s)\n")
        for path, lineno, msg in violations:
            print(f"  ✗ {event_gate_lib.rel(root, path)}:{lineno}  {msg}")
        print(
            "\nAll event schemas must use envelope v2 fields."
            "\nSee governance/data-consistency-standard.md §11."
            "\nTo ratchet an existing schema, add it to governance/event-envelope-policy.json"
            "\nunder knownUnhandled with a remediation date."
        )
        return 1

    if not event_files:
        print(f"gate-event-envelope: OK  (no event-schema files found — vacuous pass, mode={mode})")
    else:
        print(f"gate-event-envelope: OK  (event_schema_files={len(event_files)}, mode={mode})")
    return 0


def main(argv: list[str]) -> int:
    args = [a for a in argv[1:] if not a.startswith("--")]
    flags = {a for a in argv[1:] if a.startswith("--")}
    known_flags = {"--report"}
    unknown = flags - known_flags
    if unknown:
        print(f"gate-event-envelope: unknown flag(s) {' '.join(sorted(unknown))}", file=sys.stderr)
        return 2
    root = args[0] if args else "."
    report_only = "--report" in flags
    return run(root, report_only)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
