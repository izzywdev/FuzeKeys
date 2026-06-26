#!/usr/bin/env bash
# Idempotent identity-vault bring-up. Ensures Docker + containers are running, then
# initializes (once), unseals, and bootstraps OpenBao (KV v2 mount + broker policy +
# broker token). Mirrors pii-tokenizer/stack-up.sh.
#
# Safe to re-run by hand and at every logon. Persistent OpenBao (file storage) must be
# unsealed on every start; the single unseal key + root token live in
# openbao/.openbao-init.json (gitignored) and we auto-unseal from it.
set -uo pipefail
cd "$(dirname "$0")"

BAO_ADDR="${BAO_ADDR:-http://127.0.0.1:8210}"   # host port (compose maps 8210->8200)
VW_ADDR="${VW_ADDR:-http://127.0.0.1:8222}"
KEYFILE="openbao/.openbao-init.json"
KV_MOUNT="${OPENBAO_KV_MOUNT:-kv}"
BROKER_POLICY="identity-broker"

log() { echo "[idv-up $(date '+%H:%M:%S')] $*"; }
field() { python -c "import sys,json;print(json.load(sys.stdin).get(\"$1\",''))"; }
sealstatus() { curl -s "${BAO_ADDR}/v1/sys/seal-status"; }

# 1. Wait for the Docker daemon.
for i in $(seq 1 60); do
  docker info >/dev/null 2>&1 && break
  log "waiting for Docker daemon ($i)"; sleep 3
done
docker info >/dev/null 2>&1 || { log "Docker not available; abort"; exit 1; }

# 2. Ensure containers exist and match compose (idempotent).
docker compose up -d >/dev/null 2>&1 || docker-compose up -d >/dev/null 2>&1
log "containers up"

# 3. Wait for OpenBao to answer.
for i in $(seq 1 60); do
  curl -s "${BAO_ADDR}/v1/sys/seal-status" >/dev/null 2>&1 && break
  sleep 1
done
S="$(sealstatus)"; [ -z "$S" ] && { log "OpenBao not reachable; abort"; exit 1; }

# 4. Initialize once (only on a fresh, empty volume).
if [ "$(echo "$S" | field initialized)" != "True" ]; then
  log "initializing OpenBao (1 key share)"
  curl -s -X POST "${BAO_ADDR}/v1/sys/init" \
       -d '{"secret_shares":1,"secret_threshold":1}' > "$KEYFILE"
  chmod 600 "$KEYFILE" 2>/dev/null || true
  log "saved unseal key + root token to $KEYFILE (gitignored)"
fi
[ -s "$KEYFILE" ] || { log "OpenBao initialized but $KEYFILE missing — manual recovery needed"; exit 1; }

UNSEAL_KEY="$(python -c "import json;print(json.load(open('$KEYFILE'))['keys_base64'][0])")"
ROOT_TOKEN="$(python -c "import json;print(json.load(open('$KEYFILE'))['root_token'])")"

# 5. Unseal if sealed.
if [ "$(sealstatus | field sealed)" = "True" ]; then
  curl -s -X PUT "${BAO_ADDR}/v1/sys/unseal" -d "{\"key\":\"${UNSEAL_KEY}\"}" >/dev/null
  log "unsealed"
fi

H=(-s -H "X-Vault-Token: ${ROOT_TOKEN}")

# 6. Ensure KV v2 mount exists (idempotent).
curl "${H[@]}" -X POST "${BAO_ADDR}/v1/sys/mounts/${KV_MOUNT}" \
     -d '{"type":"kv","options":{"version":"2"}}' >/dev/null 2>&1 || true
log "KV v2 mount '${KV_MOUNT}/' ensured"

# 7. Ensure an audit device is enabled (best-effort).
curl "${H[@]}" -X POST "${BAO_ADDR}/v1/sys/audit/file" \
     -d '{"type":"file","options":{"file_path":"/openbao/file/audit.log"}}' >/dev/null 2>&1 || true

# 8. Write the broker policy: CRUD only on this stack's identity secrets.
POLICY_HCL="path \"${KV_MOUNT}/data/identities/*\" { capabilities = [\"create\",\"read\",\"update\",\"delete\"] }
path \"${KV_MOUNT}/metadata/identities/*\" { capabilities = [\"list\",\"read\",\"delete\"] }"
python - "$BAO_ADDR" "$ROOT_TOKEN" "$BROKER_POLICY" "$POLICY_HCL" <<'PY'
import sys, json, urllib.request
addr, token, name, hcl = sys.argv[1:5]
req = urllib.request.Request(
    f"{addr}/v1/sys/policies/acl/{name}",
    data=json.dumps({"policy": hcl}).encode(),
    headers={"X-Vault-Token": token}, method="PUT")
try:
    urllib.request.urlopen(req); print("[idv-up] broker policy written")
except Exception as e:
    print(f"[idv-up] policy write warning: {e}")
PY

# 9. Mint a broker token scoped to that policy, save to .env (idempotent overwrite).
BROKER_TOKEN="$(curl "${H[@]}" -X POST "${BAO_ADDR}/v1/auth/token/create" \
     -d "{\"policies\":[\"${BROKER_POLICY}\"],\"no_parent\":true,\"renewable\":true,\"ttl\":\"720h\"}" \
     | python -c "import sys,json;print(json.load(sys.stdin)['auth']['client_token'])" 2>/dev/null)"
if [ -n "${BROKER_TOKEN:-}" ] && [ -f .env ]; then
  python - "$BROKER_TOKEN" <<'PY'
import sys, re
tok = sys.argv[1]
s = open('.env', encoding='utf-8').read()
if re.search(r'(?m)^OPENBAO_BROKER_TOKEN=', s):
    s = re.sub(r'(?m)^OPENBAO_BROKER_TOKEN=.*$', 'OPENBAO_BROKER_TOKEN=' + tok, s)
else:
    s = s.rstrip('\n') + '\nOPENBAO_BROKER_TOKEN=' + tok + '\n'
open('.env', 'w', encoding='utf-8', newline='').write(s)
PY
  log ".env OPENBAO_BROKER_TOKEN synced"
fi

# 10. Vaultwarden readiness.
for i in $(seq 1 30); do
  curl -s "${VW_ADDR}/alive" >/dev/null 2>&1 && { log "Vaultwarden alive"; break; }
  sleep 1
done

log "done. OpenBao ${BAO_ADDR} (KV '${KV_MOUNT}/'), Vaultwarden ${VW_ADDR}."
