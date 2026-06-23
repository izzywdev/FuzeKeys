#!/usr/bin/env bash
# Enable the Vault transit engine and create the 'pii' encryption key.
# Idempotent: safe to re-run. Reads VAULT_ADDR/VAULT_TOKEN/VAULT_TRANSIT_KEY from .env.
set -euo pipefail
cd "$(dirname "$0")"
set -a; . ./.env; set +a

H=(-s -H "X-Vault-Token: ${VAULT_TOKEN}")

echo "Waiting for Vault at ${VAULT_ADDR} ..."
for i in $(seq 1 30); do
  if curl -s "${VAULT_ADDR}/v1/sys/health" >/dev/null 2>&1; then break; fi
  sleep 1
done

echo "Enabling transit secrets engine (ignore 'path already in use')..."
curl "${H[@]}" -X POST "${VAULT_ADDR}/v1/sys/mounts/transit" -d '{"type":"transit"}' || true

echo "Creating transit key '${VAULT_TRANSIT_KEY}'..."
curl "${H[@]}" -X POST "${VAULT_ADDR}/v1/transit/keys/${VAULT_TRANSIT_KEY}" -d '{"type":"aes256-gcm96"}' || true

echo
echo "Verify key:"
curl "${H[@]}" "${VAULT_ADDR}/v1/transit/keys/${VAULT_TRANSIT_KEY}" | python -c "import sys,json;d=json.load(sys.stdin);print('  key:',d.get('data',{}).get('name'),'type:',d.get('data',{}).get('type'))" 2>/dev/null || echo "  (could not read key back)"
echo "Bootstrap done."
