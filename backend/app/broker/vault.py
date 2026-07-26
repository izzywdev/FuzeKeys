"""
Vault abstraction — the system of record for root secret material.

The broker NEVER stores root secrets in Postgres and NEVER returns them. It reads
a root ONLY to *derive* a short-lived credential (see broker/derived.py). In
production this is OpenBao (KV v2 / transit) or Vaultwarden; here we define the
seam and a simple in-memory implementation for tests.
"""
from __future__ import annotations

from typing import Dict, Optional, Protocol, runtime_checkable


@runtime_checkable
class SecretResolver(Protocol):
    """Resolve a secret_ref to its ROOT material. Never exposed to callers."""

    def load_root(self, secret_ref: str) -> Optional[bytes]:
        ...


class InMemoryVault:
    """Test/dev vault. Roots live only in memory and are never serialized out."""

    def __init__(self, roots: Optional[Dict[str, bytes]] = None) -> None:
        self._roots: Dict[str, bytes] = dict(roots or {})

    def put(self, secret_ref: str, root: bytes) -> None:
        self._roots[secret_ref] = root

    def load_root(self, secret_ref: str) -> Optional[bytes]:
        return self._roots.get(secret_ref)
