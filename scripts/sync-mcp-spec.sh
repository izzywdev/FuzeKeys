#!/usr/bin/env bash
# Keep the chart's copies of the MCP inputs identical to the sources of truth.
#
# Helm can only read files inside the chart directory, so the OpenAPI document
# and the mutation overrides that the MCP gateway pod mounts have to exist twice:
#
#   contracts/openapi.yaml        -> deploy/helm/fuzekeys/files/openapi.yaml
#   mcp/tools.overrides.yaml      -> deploy/helm/fuzekeys/files/tools.overrides.yaml
#
# A silently stale copy is the failure that matters: the gateway would keep
# serving the OLD tool surface — including the OLD mutation classification — with
# nothing anywhere reporting a problem. `--check` turns that into a red build.
#
#   ./scripts/sync-mcp-spec.sh            # copy source -> chart
#   ./scripts/sync-mcp-spec.sh --check    # exit 1 if they differ; copy nothing
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEST="$ROOT/deploy/helm/fuzekeys/files"

PAIRS=(
  "contracts/openapi.yaml:openapi.yaml"
  "mcp/tools.overrides.yaml:tools.overrides.yaml"
)

if [[ "${1:-}" == "--check" ]]; then
  rc=0
  for pair in "${PAIRS[@]}"; do
    src="$ROOT/${pair%%:*}"
    dst="$DEST/${pair##*:}"
    if [[ ! -f "$dst" ]]; then
      echo "MISSING: $dst" >&2
      rc=1
    elif ! diff -q "$src" "$dst" >/dev/null; then
      echo "DRIFT: $dst differs from ${pair%%:*}" >&2
      diff -u "$src" "$dst" | head -40 >&2 || true
      rc=1
    fi
  done
  if [[ $rc -ne 0 ]]; then
    echo "" >&2
    echo "Run ./scripts/sync-mcp-spec.sh to refresh the chart's copies." >&2
    exit 1
  fi
  echo "chart MCP inputs are in sync."
  exit 0
fi

mkdir -p "$DEST"
for pair in "${PAIRS[@]}"; do
  cp "$ROOT/${pair%%:*}" "$DEST/${pair##*:}"
  echo "synced ${pair%%:*} -> deploy/helm/fuzekeys/files/${pair##*:}"
done
