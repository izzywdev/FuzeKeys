"""One-shot Vault bootstrap (containerized replacement for the host stack-up.sh Vault steps).

Waits for Vault, initializes it once (1 unseal share) writing the keys to the shared init file,
unseals from that file on every run, and ensures the transit engine + key exist. Exits 0 when done.
Persistent Vault is sealed on each start, so this runs as a one-shot service on every `compose up`.

stdlib only (no pip deps) so it can share the tokenizer image.
"""
import json
import os
import time
import urllib.request

VAULT_ADDR = os.environ.get("VAULT_ADDR", "http://vault:8200")
INIT_FILE = os.environ.get("VAULT_INIT_FILE", "/init/.vault-init.json")
TRANSIT_KEY = os.environ.get("VAULT_TRANSIT_KEY", "pii")


def _req(path, payload=None, token=None, method="GET"):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(VAULT_ADDR + path, data=data,
                                 method=method if data is None else "POST")
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("X-Vault-Token", token)
    with urllib.request.urlopen(req, timeout=15) as resp:
        body = resp.read().decode()
        return json.loads(body) if body else {}


def _seal_status():
    return _req("/v1/sys/seal-status")


def main():
    # 1. Wait for Vault to answer.
    for _ in range(60):
        try:
            status = _seal_status()
            break
        except Exception:
            time.sleep(1)
    else:
        raise SystemExit("vault-bootstrap: Vault never became reachable")

    # 2. Initialize once (fresh volume only).
    if not status.get("initialized"):
        print("vault-bootstrap: initializing Vault (1 key share)", flush=True)
        out = _req("/v1/sys/init", {"secret_shares": 1, "secret_threshold": 1})
        os.makedirs(os.path.dirname(INIT_FILE), exist_ok=True)
        with open(INIT_FILE, "w", encoding="utf-8") as fh:
            json.dump(out, fh)
        print(f"vault-bootstrap: wrote {INIT_FILE}", flush=True)

    if not os.path.exists(INIT_FILE):
        raise SystemExit("vault-bootstrap: Vault initialized but no init file to unseal from")

    keys = json.load(open(INIT_FILE, encoding="utf-8"))
    unseal_key = keys["keys_base64"][0]
    root_token = keys["root_token"]

    # 3. Unseal if sealed.
    if _seal_status().get("sealed"):
        _req("/v1/sys/unseal", {"key": unseal_key}, method="POST")
        print("vault-bootstrap: unsealed", flush=True)

    # 4. Ensure transit engine + key (idempotent).
    try:
        _req("/v1/sys/mounts/transit", {"type": "transit"}, token=root_token, method="POST")
    except Exception:
        pass  # already mounted
    try:
        _req(f"/v1/transit/keys/{TRANSIT_KEY}", {"type": "aes256-gcm96"},
             token=root_token, method="POST")
    except Exception:
        pass  # already exists
    print(f"vault-bootstrap: transit '{TRANSIT_KEY}' ready; done.", flush=True)


if __name__ == "__main__":
    main()
