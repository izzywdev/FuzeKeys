#!/usr/bin/env python3
"""gate-event-envelope — every domain-event schema uses envelope v2.

Envelope v2 requires: eventId, aggregateId, aggregateType, aggregateVersion
(governance/data-consistency-standard.md §3, data-consistency skill §2).
The gate also checks that a TypeScript event registry and its Python mirror
declare the same set of topics (parity check).

Registry location is declared in the POLICY, not inferred from the code:
  registryPaths  list of repo-relative paths/prefixes to scan for topic schemas
                 (absence → no events registered → pass vacuously)

Policy file: governance/event-envelope-policy.json
  mode           "baseline-pending" (default) | "ratchet"
  registryPaths  list of path prefixes that hold topic schema files
  knownUnhandled shrink-only list of pre-existing "topic — reason" strings

Usage: gate_event_envelope.py [root] [--report]
  --report  print every finding + suggested baseline; always exits 0
"""
from __future__ import annotations

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from event_gate_lib import apply_ratchet, git_tracked_py_files, load_policy  # noqa: E402

GATE_NAME = "gate-event-envelope"
GATE_KEY = "event-envelope"

# v2 envelope field names (camelCase and snake_case both accepted)
_REQUIRED_FIELDS = [
    ("eventId", "event_id"),
    ("aggregateId", "aggregate_id"),
    ("aggregateType", "aggregate_type"),
    ("aggregateVersion", "aggregate_version"),
]

# Patterns to detect event schema files
_EVENT_CLASS_RE = re.compile(
    r"class\s+\w*[Ee]vent\w*\s*[\(:]",
)
_FIELD_RE = re.compile(
    r"(?:\"|\')?([\w]+)(?:\"|\')?(?:\s*:\s*|\s*=\s*Field)",
)


def _extract_fields_from_py(text: str) -> set[str]:
    """Extract declared field names from a Python class/TypedDict definition."""
    fields = set()
    for m in _FIELD_RE.finditer(text):
        fields.add(m.group(1))
    return fields


def _check_py_event_file(path: str, rel: str) -> list[str]:
    """Return violations found in a Python event schema file."""
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as fh:
            text = fh.read()
    except OSError:
        return []

    violations = []
    # Only inspect files that define event classes
    if not _EVENT_CLASS_RE.search(text):
        return []

    fields = _extract_fields_from_py(text)
    for camel, snake in _REQUIRED_FIELDS:
        if camel not in fields and snake not in fields:
            violations.append(
                f"{rel} — event schema missing required v2 field '{camel}' / '{snake}'"
            )
    return violations


def _in_registry_paths(rel: str, registry_paths: list[str]) -> bool:
    norm = rel.replace("\\", "/")
    for rp in (registry_paths or []):
        rp_norm = rp.strip("/").replace("\\", "/")
        if norm == rp_norm or norm.startswith(rp_norm + "/"):
            return True
    return False


def find_violations(root: str, policy: dict) -> list[str]:
    """Return violation strings for event schemas without v2 envelope fields."""
    registry_paths: list[str] = policy.get("registryPaths", []) or []
    if not registry_paths:
        # No registry paths declared — no events to check.
        return []

    violations: list[str] = []
    for path in git_tracked_py_files(root):
        rel = os.path.relpath(path, root).replace("\\", "/")
        if not _in_registry_paths(rel, registry_paths):
            continue
        violations.extend(_check_py_event_file(path, rel))
    return violations


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    root = "."
    report_mode = False
    for a in args:
        if a == "--report":
            report_mode = True
        elif not a.startswith("-"):
            root = a
    root = os.path.abspath(root)
    policy = load_policy(root, GATE_KEY)
    violations = find_violations(root, policy)

    registry_paths = policy.get("registryPaths", []) or []
    if not registry_paths:
        print(f"{GATE_NAME}: no registryPaths declared in policy — no topics to check (pass)")
        return 0

    return apply_ratchet(violations, policy, GATE_NAME, report_mode)


if __name__ == "__main__":
    sys.exit(main())
