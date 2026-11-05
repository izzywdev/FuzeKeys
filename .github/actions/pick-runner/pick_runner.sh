#!/usr/bin/env bash
# pick_runner.sh — the ONE implementation of the fleet's hosted-default runner chooser.
#
# Every `pick-runner` job in workflow-templates/ (and the hub's own copies) calls this through
# .github/actions/pick-runner. Do not re-inline it into a workflow: the inlined copies are how
# the literal `fuze-runner` label and the online-runner probe were copy-pasted into every
# template and then broke every repo except FuzeSDLC (governance/ci-runners.md).
#
# Inputs (environment):
#   FORCE_RUNNER     vars.HARDEN_GATE_RUNNER — force override, wins over everything.
#   CI_RUNNER_POOL   vars.CI_RUNNER_POOL     — per-repo override of the pool NAME.
#   IS_PRIVATE       github.event.repository.private ("true" / anything else).
#   OWNER            github.repository_owner.
#   BUDGET_TOKEN     secrets.CI_BUDGET_TOKEN — optional Actions-billing read token.
#   GITHUB_REPOSITORY, GITHUB_OUTPUT — set by the runner.
#
# Output: `runner=<label>` appended to $GITHUB_OUTPUT.
#
# Usage: pick_runner.sh            choose and emit
#        pick_runner.sh --pool     print the resolved pool name only (tests, debugging)
set -euo pipefail

# The repo's self-hosted ARC pool (scale-set name). Resolution order:
#   1. vars.CI_RUNNER_POOL, when set;
#   2. FuzeSDLC -> `fuze-runner` (the one set that carries that name);
#   3. otherwise the lowercased repository name (FuzeFinance -> `fuzefinance`).
# The ARC controller watches a single namespace (`arc-runners`) and an AutoscalingRunnerSet
# is named after its runnerScaleSetName, so only ONE set per namespace can be `fuze-runner`;
# every other repo's set is named after the repo. FuzeInfra owns these names
# (argocd/applications/arc-runners.yaml in FuzeInfra).
# Keep in lockstep with scripts/bootstrap/lib/runner_pool.py (parity-tested).
resolve_pool() {
  if [ -n "${CI_RUNNER_POOL:-}" ]; then
    printf '%s\n' "${CI_RUNNER_POOL}"; return
  fi
  local name="${GITHUB_REPOSITORY:?GITHUB_REPOSITORY is not set}"
  name="${name#*/}"
  name="$(printf '%s' "${name}" | tr '[:upper:]' '[:lower:]')"
  if [ "${name}" = "fuzesdlc" ]; then
    printf '%s\n' "fuze-runner"; return
  fi
  printf '%s\n' "${name}"
}

if [ "${1:-}" = "--pool" ]; then
  resolve_pool; exit 0
fi

emit() { echo "runner=$1" >> "${GITHUB_OUTPUT:?GITHUB_OUTPUT is not set}"; echo "selected runner: $1"; }

if [ -n "${FORCE_RUNNER:-}" ]; then
  emit "${FORCE_RUNNER}"; exit 0
fi
# Public repos: Actions is free and unmetered — always hosted.
if [ "${IS_PRIVATE:-}" != "true" ]; then
  emit ubuntu-latest; exit 0
fi

pool="$(resolve_pool)"

# NO ONLINE-RUNNER PROBE, DELIBERATELY. The ARC scale sets run `minRunners: 0` and scale up
# from zero when a job names them, so an idle, healthy pool reports 0 runners online. The old
# probe read that as "down" and routed to ubuntu-latest, which on a budget-exhausted private
# repo never starts. A pool at 0 runners is available.
if [ -z "${BUDGET_TOKEN:-}" ]; then
  echo "::notice title=pick-runner::no CI_BUDGET_TOKEN; using the self-hosted pool '${pool}' (free, not budget-gated)"
  emit "${pool}"; exit 0
fi

resp="$(curl -sS -H "Authorization: Bearer ${BUDGET_TOKEN}" -H "Accept: application/vnd.github+json" "https://api.github.com/orgs/${OWNER}/settings/billing/actions" || true)"
used="$(printf '%s' "${resp}" | jq -r '.total_minutes_used // empty' 2>/dev/null || true)"
incl="$(printf '%s' "${resp}" | jq -r '.included_minutes // empty' 2>/dev/null || true)"
if printf '%s' "${used}" | grep -qE '^[0-9]+$' && printf '%s' "${incl}" | grep -qE '^[0-9]+$' && [ "${used}" -lt "${incl}" ]; then
  emit ubuntu-latest
else
  echo "::notice title=pick-runner::Actions budget exhausted or unreadable (used=${used:-?} incl=${incl:-?}) — using the self-hosted pool '${pool}'"
  emit "${pool}"
fi
