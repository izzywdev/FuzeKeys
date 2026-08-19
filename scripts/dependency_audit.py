#!/usr/bin/env python3
"""Dependency vulnerability gate for FuzeKeys.

Runs pip-audit over the backend requirements and `npm audit` over the frontend,
then compares the advisories found against a checked-in baseline.

Why a baseline rather than a plain pass/fail: the backend pins a 2023-era
dependency set and the frontend builds on react-scripts 5.0.1 (Create React App,
unmaintained), so both ecosystems carry a large set of *pre-existing* advisories
whose only fixes are major-version migrations. A gate that fails on all of them
fails on every pull request and stops being read. Baselining makes the gate
answer the question that actually matters on a PR -- "did this change introduce a
new vulnerable dependency?" -- while keeping the existing debt enumerated in one
reviewable file that can be burned down.

Exit codes:
    0  no advisories outside the baseline
    1  at least one advisory is not in the baseline (or a scanner failed)

Refresh the baseline deliberately, never as a reflex:
    python scripts/dependency_audit.py --update-baseline
"""

from __future__ import annotations

import argparse
import json
import pathlib
import subprocess
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
BASELINE_PATH = REPO_ROOT / "security" / "dependency-audit-baseline.json"
BACKEND_REQUIREMENTS = REPO_ROOT / "backend" / "requirements.txt"
FRONTEND_DIR = REPO_ROOT / "frontend"


def _run(cmd: list[str], cwd: pathlib.Path) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)


def collect_python_advisories() -> tuple[dict[str, dict], str | None]:
    """Return {advisory_id: metadata} for the pinned backend requirements."""
    proc = _run(
        [
            "pip-audit",
            "-r",
            str(BACKEND_REQUIREMENTS),
            "--progress-spinner",
            "off",
            "-f",
            "json",
        ],
        REPO_ROOT,
    )
    if not proc.stdout.strip():
        return {}, f"pip-audit produced no output (exit {proc.returncode}): {proc.stderr[-2000:]}"

    try:
        report = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        return {}, f"could not parse pip-audit output: {exc}"

    found: dict[str, dict] = {}
    for dep in report.get("dependencies", []):
        for vuln in dep.get("vulns") or []:
            found[vuln["id"]] = {
                "package": dep["name"],
                "version": dep.get("version", ""),
                "fix_versions": vuln.get("fix_versions") or [],
            }
    return found, None


def collect_npm_advisories() -> tuple[dict[str, dict], str | None]:
    """Return {advisory_id: metadata} for the frontend dependency tree."""
    proc = _run(["npm", "audit", "--json"], FRONTEND_DIR)
    if not proc.stdout.strip():
        return {}, f"npm audit produced no output (exit {proc.returncode}): {proc.stderr[-2000:]}"

    try:
        report = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        return {}, f"could not parse npm audit output: {exc}"

    found: dict[str, dict] = {}
    for name, info in (report.get("vulnerabilities") or {}).items():
        for via in info.get("via", []):
            if not isinstance(via, dict):
                continue  # a string here is just a transitive parent package
            source = via.get("source")
            if source is None:
                continue
            found[str(source)] = {
                "package": via.get("name", name),
                "severity": via.get("severity", ""),
                "title": via.get("title", ""),
            }
    return found, None


def load_baseline() -> dict:
    if not BASELINE_PATH.exists():
        return {"python": {}, "npm": {}}
    return json.loads(BASELINE_PATH.read_text())


def report(ecosystem: str, found: dict[str, dict], baseline: dict[str, dict]) -> list[str]:
    """Print a summary and return the advisory ids that are not baselined."""
    new = sorted(set(found) - set(baseline))
    stale = sorted(set(baseline) - set(found))

    print(f"\n{ecosystem}: {len(found)} advisories, {len(baseline)} baselined")
    for advisory_id in new:
        meta = found[advisory_id]
        detail = " ".join(f"{k}={v}" for k, v in meta.items() if v)
        print(f"  NEW  {advisory_id}  {detail}")
    if stale:
        print(
            f"  {len(stale)} baselined advisories no longer present -- "
            f"run --update-baseline to drop them: {', '.join(stale[:10])}"
            + (" ..." if len(stale) > 10 else "")
        )
    return new


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--update-baseline",
        action="store_true",
        help="rewrite the baseline from the current scan results",
    )
    args = parser.parse_args()

    python_found, python_err = collect_python_advisories()
    npm_found, npm_err = collect_npm_advisories()

    for err in (python_err, npm_err):
        if err:
            print(f"ERROR: {err}", file=sys.stderr)
            return 1

    if args.update_baseline:
        BASELINE_PATH.parent.mkdir(parents=True, exist_ok=True)
        BASELINE_PATH.write_text(
            json.dumps(
                {
                    "_comment": (
                        "Known, pre-existing dependency advisories. The gate in "
                        "scripts/dependency_audit.py fails on anything NOT listed "
                        "here, so a pull request that introduces a new vulnerable "
                        "dependency is blocked. Entries are debt to burn down, not "
                        "an approval -- shrink this file, do not grow it."
                    ),
                    "python": python_found,
                    "npm": npm_found,
                },
                indent=2,
                sort_keys=True,
            )
            + "\n"
        )
        print(
            f"Baseline written: {len(python_found)} python, {len(npm_found)} npm "
            f"-> {BASELINE_PATH.relative_to(REPO_ROOT)}"
        )
        return 0

    baseline = load_baseline()
    new_python = report("python (pip-audit)", python_found, baseline.get("python", {}))
    new_npm = report("npm (npm audit)", npm_found, baseline.get("npm", {}))

    if new_python or new_npm:
        print(
            f"\nFAIL: {len(new_python) + len(new_npm)} advisory(ies) outside the "
            "baseline. Upgrade the dependency, or -- if it is genuinely "
            "unavoidable -- refresh the baseline in its own reviewed commit."
        )
        return 1

    print("\nOK: no dependency advisories outside the baseline.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
