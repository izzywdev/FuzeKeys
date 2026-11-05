#!/usr/bin/env python3
"""gate-event-envelope — data-consistency standard §11.

Every topic schema registered in the repo's topic registry must carry
the envelope-v2 required fields: eventId, aggregateId, aggregateType.

The registry location is declared in governance/event-envelope-policy.json
under registryPaths (list of glob patterns, relative to repo root).
If registryPaths is empty or absent there is nothing to check: exit 0.

Operates as a RATCHET:
  baseline-pending (seeded default) — scan, warn, suggest baseline, exit 0.
  ratchet                           — new violations fail; known ones warn.

Usage:
  gate_event_envelope.py [root]            enforce (ratchet or baseline-pending)
  gate_event_envelope.py [root] --report   report-only (always exit 0)
"""
from __future__ import annotations

import glob
import json
import os
import sys

try:
    import yaml  # type: ignore
except Exception:
    yaml = None

ENVELOPE_V2_FIELDS = ("eventId", "aggregateId", "aggregateType")

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
from event_gate_lib import load_policy, run_ratchet  # noqa: E402


def _load_schema_file(path: str) -> dict | None:
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as fh:
            text = fh.read()
        if path.endswith(".json"):
            return json.loads(text)
        if yaml is not None:
            return yaml.safe_load(text)
        return json.loads(text)
    except Exception:
        return None


def _has_envelope_fields(schema: object) -> bool:
    """True when the schema (or its properties) declares all envelope-v2 fields."""
    if not isinstance(schema, dict):
        return False
    props = schema.get("properties", {}) or {}
    if all(f in props for f in ENVELOPE_V2_FIELDS):
        return True
    # Allow the envelope to live one level deeper (e.g. a wrapper with a `data` key)
    for _key, sub in props.items():
        if isinstance(sub, dict) and _has_envelope_fields(sub):
            return True
    return False


def find_registry_files(root: str, registry_paths: list[str]) -> list[str]:
    """Expand glob patterns relative to root; return matched file paths."""
    found: list[str] = []
    for pattern in registry_paths:
        expanded = glob.glob(os.path.join(root, pattern), recursive=True)
        found.extend(expanded)
    return sorted(set(found))


def check_registry(root: str, registry_paths: list[str]) -> list[tuple[str, int, str]]:
    """Return one finding per schema file that is missing envelope-v2 fields."""
    findings: list[tuple[str, int, str]] = []
    for filepath in find_registry_files(root, registry_paths):
        schema = _load_schema_file(filepath)
        if schema is None:
            continue
        if not _has_envelope_fields(schema):
            relpath = os.path.relpath(filepath, root).replace("\\", "/")
            missing = [f for f in ENVELOPE_V2_FIELDS
                       if f not in (schema.get("properties", {}) or {})]
            findings.append((relpath, 0, f"missing envelope-v2 fields: {missing}"))
    return findings


def main() -> int:
    args = sys.argv[1:]
    report_only = "--report" in args
    pos = [a for a in args if not a.startswith("-")]
    root = pos[0] if pos else "."

    policy = load_policy(root, "event-envelope")
    registry_paths: list[str] = policy.get("registryPaths", []) or []

    if not registry_paths:
        print("gate-event-envelope: no registryPaths configured — nothing to check (pass)")
        return 0

    findings = check_registry(root, registry_paths)

    if report_only:
        if findings:
            print(f"gate-event-envelope (report): {len(findings)} finding(s)")
            for relpath, _lineno, msg in findings:
                print(f"  {relpath}: {msg}")
        else:
            print("gate-event-envelope (report): no findings")
        return 0

    return run_ratchet(findings, policy, "gate-event-envelope")


if __name__ == "__main__":
    sys.exit(main())
