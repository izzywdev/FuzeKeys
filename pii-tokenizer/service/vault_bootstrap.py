"""One-shot Vault bootstrap (containerized replacement for the host stack-up.sh Vault steps).

Waits for Vault, initializes it once (1 unseal share) writing the keys to the shared init file,
unseals from that file on every run, and ensures the transit engine + key exist. Exits 0 when done.
Persistent Vault is sealed on each start, so this runs as a one-shot service on every `compose up`.

stdlib only (no pip deps) so it can share the tokenizer image.
"""
import base64
import json
import os
import ssl
import time
import urllib.error
import urllib.request

VAULT_ADDR = os.environ.get("VAULT_ADDR", "http://vault:8200")
INIT_FILE = os.environ.get("VAULT_INIT_FILE", "/init/.vault-init.json")
TRANSIT_KEY = os.environ.get("VAULT_TRANSIT_KEY", "pii")
KV_MOUNT = os.environ.get("VAULT_KV_MOUNT", "secret")
RUNTIME_SECRET = os.environ.get("VAULT_RUNTIME_SECRET", "fuzekeys-vault-runtime")
K8S_NAMESPACE = os.environ.get("KUBERNETES_NAMESPACE", "default")


def _req(path, payload=None, token=None, method="GET"):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(
        VAULT_ADDR + path, data=data, method=method if data is None else "POST"
    )
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("X-Vault-Token", token)
    with urllib.request.urlopen(req, timeout=15) as resp:
        body = resp.read().decode()
        return json.loads(body) if body else {}


def _seal_status():
    return _req("/v1/sys/seal-status")


def _publish_runtime_token(token):
    """Create or replace the namespaced Secret consumed by the backend pod."""
    host = os.environ.get("KUBERNETES_SERVICE_HOST")
    port = os.environ.get("KUBERNETES_SERVICE_PORT_HTTPS", "443")
    if not host:
        raise RuntimeError("Kubernetes service environment is unavailable")
    service_token = (
        open("/var/run/secrets/kubernetes.io/serviceaccount/token", encoding="utf-8")
        .read()
        .strip()
    )
    ca_file = "/var/run/secrets/kubernetes.io/serviceaccount/ca.crt"
    url = f"https://{host}:{port}/api/v1/namespaces/{K8S_NAMESPACE}/secrets"
    payload = {
        "apiVersion": "v1",
        "kind": "Secret",
        "metadata": {"name": RUNTIME_SECRET, "namespace": K8S_NAMESPACE},
        "type": "Opaque",
        "data": {"token": base64.b64encode(token.encode()).decode()},
    }
    headers = {
        "Authorization": f"Bearer {service_token}",
        "Content-Type": "application/json",
    }
    context = ssl.create_default_context(cafile=ca_file)
    get_req = urllib.request.Request(f"{url}/{RUNTIME_SECRET}", headers=headers)
    try:
        with urllib.request.urlopen(get_req, timeout=15, context=context):
            exists = True
    except urllib.error.HTTPError as exc:
        if exc.code != 404:
            raise
        exists = False
    target = f"{url}/{RUNTIME_SECRET}" if exists else url
    method = "PUT" if exists else "POST"
    request = urllib.request.Request(
        target, data=json.dumps(payload).encode(), headers=headers, method=method
    )
    with urllib.request.urlopen(request, timeout=15, context=context):
        pass


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
        raise SystemExit(
            "vault-bootstrap: Vault initialized but no init file to unseal from"
        )

    keys = json.load(open(INIT_FILE, encoding="utf-8"))
    unseal_key = keys["keys_base64"][0]
    root_token = keys["root_token"]

    # 3. Unseal if sealed.
    if _seal_status().get("sealed"):
        _req("/v1/sys/unseal", {"key": unseal_key}, method="POST")
        print("vault-bootstrap: unsealed", flush=True)

    # 4. Ensure transit engine + key (idempotent).
    try:
        _req(
            "/v1/sys/mounts/transit",
            {"type": "transit"},
            token=root_token,
            method="POST",
        )
    except Exception:
        pass  # already mounted
    try:
        _req(
            f"/v1/transit/keys/{TRANSIT_KEY}",
            {"type": "aes256-gcm96"},
            token=root_token,
            method="POST",
        )
    except Exception:
        pass  # already exists
    # 5. Ensure a KV-v2 mount for per-user connector grants. FuzeKeys backend
    # receives a separately provisioned least-privilege token; it never reads
    # the root token or this init file.
    try:
        _req(
            f"/v1/sys/mounts/{KV_MOUNT}",
            {"type": "kv", "options": {"version": "2"}},
            token=root_token,
            method="POST",
        )
    except Exception:
        pass  # already mounted

    # 6. Issue a non-root token constrained to connector credential paths and
    # publish it as a namespaced Kubernetes Secret for the backend.
    policy_name = "fuzekeys-connectors"
    policy = (
        f'path "{KV_MOUNT}/data/connectors/*" {{ capabilities = ["create", "read", "update", "delete"] }}\n'
        f'path "{KV_MOUNT}/metadata/connectors/*" {{ capabilities = ["read", "delete"] }}\n'
    )
    _req(
        f"/v1/sys/policies/acl/{policy_name}",
        {"policy": policy},
        token=root_token,
        method="PUT",
    )
    issued = _req(
        "/v1/auth/token/create-orphan",
        {"policies": [policy_name], "no_default_policy": True, "ttl": "720h"},
        token=root_token,
        method="POST",
    )
    _publish_runtime_token(issued["auth"]["client_token"])
    print(
        f"vault-bootstrap: transit '{TRANSIT_KEY}', kv-v2 '{KV_MOUNT}', and scoped backend token ready; done.",
        flush=True,
    )


if __name__ == "__main__":
    main()
