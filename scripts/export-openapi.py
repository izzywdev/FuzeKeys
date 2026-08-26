#!/usr/bin/env python3
"""Export FuzeKeys' OpenAPI document to ``contracts/openapi.yaml``.

WHY THIS IS DERIVED AND NOT HAND-WRITTEN
----------------------------------------
The FastAPI application IS the API. A hand-authored contract for 65 paths would
be wrong within a week and nobody would notice, because nothing compares the two.
Deriving the document from the running application makes "the contract describes
the real endpoints" a property of the build rather than a promise in a review.

``--check`` re-derives the document and compares the set of ``(method, path)``
operations against the committed ``contracts/openapi.yaml``. It exits non-zero
when they differ, which is the only failure mode that matters downstream: the
MCP gateway turns every operation in the committed document into a tool, so an
operation that exists in the code but not in the contract is an invisible tool,
and one in the contract but not the code is a tool that 404s.

The comparison deliberately ignores schemas and ``operationId`` (see below) —
this is a coverage gate, not a byte-diff.

OPERATION IDs
-------------
FastAPI's auto-generated ``operationId`` (``get_account_credentials_api_
credentials_account__account_id__credentials_get``) is up to 76 characters, and
the MCP gateway truncates tool names at 64 — two different operations can
therefore collide into one tool name. The live application also currently emits
DUPLICATE operationIds for two accounts routes (FastAPI warns about it at
startup). So this script assigns its own deterministic, readable id derived from
``METHOD + path``, which is unique by construction and short:

    GET /api/credentials/account/{account_id}/credentials
      -> get_credentials_account_by_account_id_credentials

The application's own ``/openapi.json`` keeps FastAPI's ids. That divergence is
intentional and narrow: ``operationId`` is metadata, not API shape, and fixing it
in the application would mean editing routers another workstream is currently
rewriting.

Usage:
    python scripts/export-openapi.py            # write contracts/openapi.yaml
    python scripts/export-openapi.py --check    # verify no drift, write nothing

Run it from the repo root with the backend's dependencies importable.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND = REPO_ROOT / "backend"
CONTRACT = REPO_ROOT / "contracts" / "openapi.yaml"

HTTP_METHODS = ("get", "put", "post", "delete", "patch", "head", "options", "trace")


def operation_id(method: str, path: str) -> str:
    """Deterministic, unique-by-construction, MCP-legal operation id.

    Mirrors the gateway's own fallback naming (``<method>_<slugged path>``) so a
    reader of the tool list can map a tool straight back to an HTTP route.
    """
    slug = path
    for prefix in ("/api/v1/", "/api/"):
        if slug.startswith(prefix):
            slug = slug[len(prefix):]
            break
    out = []
    i = 0
    while i < len(slug):
        ch = slug[i]
        if ch == "{":
            end = slug.index("}", i)
            out.append("by_" + slug[i + 1:end])
            i = end + 1
        else:
            out.append(ch)
            i += 1
    slug = "".join(out)
    cleaned = "".join(c if c.isalnum() else "_" for c in slug).strip("_")
    while "__" in cleaned:
        cleaned = cleaned.replace("__", "_")
    name = f"{method.lower()}_{cleaned}" if cleaned else f"{method.lower()}_root"
    return name[:64]


def build_spec() -> dict:
    sys.path.insert(0, str(BACKEND))
    from app.main import app  # noqa: E402  (import after sys.path fix)

    spec = app.openapi()

    # Trim the marketing prose out of `info.description`: it is rendered into
    # every MCP client's server description and says nothing an agent can use.
    info = spec.setdefault("info", {})
    info["description"] = (
        "FuzeKeys — identity and credential vault. Managed digital identities, "
        "per-site accounts, encrypted vault assets, capability-token secret "
        "brokering, and automated signup workflows.\n\n"
        "DERIVED DOCUMENT: regenerate with `python scripts/export-openapi.py`. "
        "Do not hand-edit."
    )
    info.pop("termsOfService", None)
    info.pop("contact", None)

    seen: dict[str, str] = {}
    for path, item in spec.get("paths", {}).items():
        for method in HTTP_METHODS:
            op = item.get(method)
            if not isinstance(op, dict):
                continue
            oid = operation_id(method, path)
            if oid in seen:
                raise SystemExit(
                    f"operationId collision: {oid} claimed by {seen[oid]} and "
                    f"{method.upper()} {path}"
                )
            seen[oid] = f"{method.upper()} {path}"
            op["operationId"] = oid
    return spec


def operations(spec: dict) -> set[str]:
    return {
        f"{method.upper()} {path}"
        for path, item in (spec.get("paths") or {}).items()
        for method in HTTP_METHODS
        if isinstance(item.get(method), dict)
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="compare against the committed contract; write nothing",
    )
    args = parser.parse_args()

    import yaml

    spec = build_spec()

    if args.check:
        if not CONTRACT.exists():
            print(f"MISSING: {CONTRACT} does not exist", file=sys.stderr)
            return 1
        committed = yaml.safe_load(CONTRACT.read_text(encoding="utf-8"))
        live, on_disk = operations(spec), operations(committed)
        missing = sorted(live - on_disk)
        extra = sorted(on_disk - live)
        if missing or extra:
            for m in missing:
                print(f"MISSING FROM CONTRACT: {m}", file=sys.stderr)
            for e in extra:
                print(f"NOT IN THE APPLICATION: {e}", file=sys.stderr)
            print(
                "\ncontracts/openapi.yaml is out of date — run "
                "`python scripts/export-openapi.py`.",
                file=sys.stderr,
            )
            return 1
        print(f"contracts/openapi.yaml is current ({len(live)} operations).")
        return 0

    CONTRACT.parent.mkdir(parents=True, exist_ok=True)
    CONTRACT.write_text(
        "# GENERATED — do not hand-edit.\n"
        "# Source of truth: the FastAPI application (backend/app/main.py).\n"
        "# Regenerate: python scripts/export-openapi.py\n"
        "# Verify:     python scripts/export-openapi.py --check\n"
        + yaml.safe_dump(spec, sort_keys=False, width=100, allow_unicode=True),
        encoding="utf-8",
    )
    print(f"wrote {CONTRACT} ({len(operations(spec))} operations)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
