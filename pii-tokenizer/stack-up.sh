#!/usr/bin/env bash
# Idempotent PII stack bring-up. Ensures Docker + containers are running, then
# initializes (once), unseals, and bootstraps the Vault transit engine.
#
# Safe to run at every logon (registered as a scheduled task) and to re-run by hand.
# Persistent Vault (file storage) must be unsealed on every start; we keep a single
# unseal key + the root token in vault/.vault-init.json (gitignored) and auto-unseal
# from it. That key file is the crown jewel of a localhost-only dev trust model —
# without it, a persisted-but-sealed Vault cannot be recovered.
set -uo pipefail
cd "$(dirname "$0")"

VAULT_ADDR="${VAULT_ADDR:-http://127.0.0.1:8200}"
KEYFILE="vault/.vault-init.json"
TRANSIT_KEY="$(grep -E '^VAULT_TRANSIT_KEY=' .env 2>/dev/null | cut -d= -f2)"
TRANSIT_KEY="${TRANSIT_KEY:-pii}"

log() { echo "[stack-up $(date '+%H:%M:%S')] $*"; }
field() { python -c "import sys,json;print(json.load(sys.stdin).get(\"$1\",''))"; }
sealstatus() { curl -s "${VAULT_ADDR}/v1/sys/seal-status"; }

# 1. Wait for the Docker daemon (Docker Desktop can be slow after logon).
for i in $(seq 1 60); do
  docker info >/dev/null 2>&1 && break
  log "waiting for Docker daemon ($i)"; sleep 3
done
docker info >/dev/null 2>&1 || { log "Docker not available; abort"; exit 1; }

# 2. Ensure containers exist and match compose (idempotent; applies compose changes).
docker compose up -d >/dev/null 2>&1 || docker-compose up -d >/dev/null 2>&1
log "containers up"

# 3. Wait for Vault to answer.
for i in $(seq 1 60); do
  curl -s "${VAULT_ADDR}/v1/sys/seal-status" >/dev/null 2>&1 && break
  sleep 1
done
S="$(sealstatus)"; [ -z "$S" ] && { log "Vault not reachable; abort"; exit 1; }

# 4. Initialize once (only on a fresh, empty volume).
if [ "$(echo "$S" | field initialized)" != "True" ]; then
  log "initializing Vault (1 key share)"
  curl -s -X POST "${VAULT_ADDR}/v1/sys/init" \
       -d '{"secret_shares":1,"secret_threshold":1}' > "$KEYFILE"
  chmod 600 "$KEYFILE" 2>/dev/null || true
  log "saved unseal key + root token to $KEYFILE (gitignored)"
fi
[ -s "$KEYFILE" ] || { log "Vault initialized but $KEYFILE missing — cannot auto-unseal; manual recovery needed"; exit 1; }

UNSEAL_KEY="$(python -c "import json;print(json.load(open('$KEYFILE'))['keys_base64'][0])")"
ROOT_TOKEN="$(python -c "import json;print(json.load(open('$KEYFILE'))['root_token'])")"

# 5. Unseal if sealed.
if [ "$(sealstatus | field sealed)" = "True" ]; then
  curl -s -X PUT "${VAULT_ADDR}/v1/sys/unseal" -d "{\"key\":\"${UNSEAL_KEY}\"}" >/dev/null
  log "unsealed"
fi

# 6. Sync .env VAULT_TOKEN to the persistent root token (init mints a new one).
if grep -qE '^VAULT_TOKEN=' .env 2>/dev/null; then
  python - "$ROOT_TOKEN" <<'PY'
import sys, re
tok = sys.argv[1]
s = open('.env', encoding='utf-8').read()
s = re.sub(r'(?m)^VAULT_TOKEN=.*$', 'VAULT_TOKEN=' + tok, s)
open('.env', 'w', encoding='utf-8', newline='').write(s)
PY
  log ".env VAULT_TOKEN synced to persistent root token"
fi

# 7. Ensure transit engine + key exist (idempotent).
H=(-s -H "X-Vault-Token: ${ROOT_TOKEN}")
curl "${H[@]}" -X POST "${VAULT_ADDR}/v1/sys/mounts/transit" -d '{"type":"transit"}' >/dev/null 2>&1 || true
curl "${H[@]}" -X POST "${VAULT_ADDR}/v1/transit/keys/${TRANSIT_KEY}" -d '{"type":"aes256-gcm96"}' >/dev/null 2>&1 || true
NAME="$(curl "${H[@]}" "${VAULT_ADDR}/v1/transit/keys/${TRANSIT_KEY}" | field data 2>/dev/null)"
log "transit '${TRANSIT_KEY}' present: $([ -n "$NAME" ] && echo yes || echo NO)"
log "done."
