"""
Vault abstraction — the system of record for root secret material.

The broker NEVER stores root secrets in Postgres and NEVER returns them. It reads
a root ONLY to *derive* a short-lived credential (see broker/derived.py). In
production this is OpenBao (KV v2 / transit) or Vaultwarden; here we define the
seam and a simple in-memory implementation for tests.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Dict, Mapping, Optional, Protocol, runtime_checkable


@runtime_checkable
class SecretResolver(Protocol):
    """Resolve a secret_ref to its ROOT material. Never exposed to callers."""

    def load_root(self, secret_ref: str) -> Optional[bytes]:
        ...


@runtime_checkable
class MutableSecretVault(SecretResolver, Protocol):
    """Vault seam used by connector OAuth flows. Values never enter Postgres."""

    def put(self, secret_ref: str, root: bytes) -> None:
        ...

    def delete(self, secret_ref: str) -> None:
        ...


class InMemoryVault:
    """Test/dev vault. Roots live only in memory and are never serialized out."""

    def __init__(self, roots: Optional[Dict[str, bytes]] = None) -> None:
        self._roots: Dict[str, bytes] = dict(roots or {})

    def put(self, secret_ref: str, root: bytes) -> None:
        self._roots[secret_ref] = root

    def load_root(self, secret_ref: str) -> Optional[bytes]:
        return self._roots.get(secret_ref)

    def delete(self, secret_ref: str) -> None:
        self._roots.pop(secret_ref, None)


class OpenBaoKV2Vault:
    """Minimal OpenBao/Vault KV-v2 adapter.

    ``secret_ref`` is a logical path such as ``connectors/<user>/google-gmail``.
    The adapter deliberately exposes only opaque bytes to the rest of FuzeKeys.
    """

    def __init__(self, address: str, token: str, mount: str = "secret", namespace: str = ""):
        self.address = address.rstrip("/")
        self.token = token
        self.mount = mount.strip("/")
        self.namespace = namespace

    def _request(self, method: str, suffix: str, payload: Optional[Mapping] = None):
        body = json.dumps(payload).encode() if payload is not None else None
        headers = {"X-Vault-Token": self.token, "Content-Type": "application/json"}
        if self.namespace:
            headers["X-Vault-Namespace"] = self.namespace
        request = urllib.request.Request(
            f"{self.address}/v1/{self.mount}/{suffix.lstrip('/')}",
            data=body,
            headers=headers,
            method=method,
        )
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                raw = response.read()
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return None
            raise RuntimeError(f"vault request failed with status {exc.code}") from exc

    def put(self, secret_ref: str, root: bytes) -> None:
        encoded = root.decode("utf-8")
        self._request("POST", f"data/{urllib.parse.quote(secret_ref, safe='/')}", {"data": {"value": encoded}})

    def load_root(self, secret_ref: str) -> Optional[bytes]:
        result = self._request("GET", f"data/{urllib.parse.quote(secret_ref, safe='/')}")
        if not result:
            return None
        value = result.get("data", {}).get("data", {}).get("value")
        return value.encode("utf-8") if isinstance(value, str) else None

    def delete(self, secret_ref: str) -> None:
        self._request("DELETE", f"metadata/{urllib.parse.quote(secret_ref, safe='/')}")
