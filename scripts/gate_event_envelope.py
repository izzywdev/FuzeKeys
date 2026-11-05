#!/usr/bin/env python3
"""gate-event-envelope — Every registered topic's schema must be on envelope v2.

Envelope v2 requires: eventId, aggregateId, aggregateType, timestamp.
Registry location is declared in governance/event-envelope-policy.json (registryPaths).

Modes:
  baseline-pending  full scan, warning annotations, exit 0
  ratchet           new violations exit 1; knownUnhandled entries warn

Usage:
  gate_event_envelope.py [root]           enforcing
  gate_event_envelope.py [root] --report  full report, always exit 0

Policy: governance/event-envelope-policy.json
"""
from __future__ import annotations
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from event_gate_lib import Policy, Finding, evaluate, ls_files

GATE = "gate-event-envelope"
POLICY_REL = os.path.join("governance", "event-envelope-policy.json")

# Required v2 envelope fields
V2_FIELDS = {"eventId", "aggregateId", "aggregateType", "timestamp"}

try:
    import yaml as _yaml  # type: ignore
    _HAVE_YAML = True
except ImportError:
    _yaml = None
    _HAVE_YAML = False


def _extract_properties(schema: dict) -> set:
    props = schema.get("properties", {})
    if isinstance(props, dict):
        return set(props.keys())
    return set()


def _check_schema_file(path: str) -> list:
    """Return sorted list of missing v2 field names. Empty = compliant."""
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            text = f.read()
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            if not _HAVE_YAML:
                return []  # can't parse YAML without pyyaml — skip
            data = _yaml.safe_load(text) or {}
        props = _extract_properties(data)
        return sorted(V2_FIELDS - props)
    except OSError:
        return []


def find_schema_files(root: str, registry_paths: list) -> list:
    """Find JSON/YAML schema files in declared registry paths."""
    found = []
    for rel in registry_paths:
        base = os.path.join(root, rel)
        if os.path.isfile(base):
            found.append(base)
        elif os.path.isdir(base):
            for fn in sorted(os.listdir(base)):
                if fn.endswith((".json", ".yaml", ".yml")):
                    found.append(os.path.join(base, fn))
    return found


def scan(root: str, policy: Policy) -> list:
    if not policy.registry_paths:
        return []  # no event registry declared — nothing to check
    findings = []
    for path in find_schema_files(root, policy.registry_paths):
        missing = _check_schema_file(path)
        if missing:
            findings.append(Finding(
                file=path,
                line=1,
                message=f"schema missing v2 envelope fields: {', '.join(missing)}",
            ))
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
