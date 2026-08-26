"""
Runtime wiring for the broker's HTTP/MCP surfaces.

The BrokerService core is synchronous (see service.py) for testability, so the
HTTP surface uses a SYNCHRONOUS SQLAlchemy session built from the same
``DATABASE_URL`` (normalized to a psycopg2 driver), and FastAPI runs the broker
path-operations in a threadpool.

SECURITY — transport identity comes from the trusted identity plane, never the
request body. A fronting gateway / the FuzeKeys identity plane verifies the OIDC
token or mTLS peer cert and passes the RESULT in gateway-verified headers:
  - ``X-Verified-Repo``   -> OIDC ``repo`` claim (e.g. "izzywdev/FuzeAgent")
  - ``X-Verified-Spiffe`` -> mTLS/SPIFFE peer subject
These headers must be stripped from untrusted ingress by the gateway; the broker
trusts them only because the gateway sets them after verification. If neither is
present the broker fails closed.
"""
from __future__ import annotations

import functools
import os
from typing import Optional

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from .identity import TransportContext, TransportIdentity
from .service import BrokerConfig, BrokerService
from .vault import InMemoryVault, SecretResolver


def _sync_database_url() -> str:
    url = os.getenv(
        "DATABASE_URL",
        "postgresql+psycopg2://fuzekeys_user:fuzekeys_password@localhost:5432/fuzekeys",
    )
    # Normalize async drivers to a sync psycopg2 driver for the broker's session.
    return url.replace("+asyncpg", "+psycopg2").replace(
        "postgresql://", "postgresql+psycopg2://"
    )


@functools.lru_cache(maxsize=1)
def _session_factory() -> sessionmaker:
    engine = create_engine(_sync_database_url(), pool_pre_ping=True, future=True)
    return sessionmaker(bind=engine, expire_on_commit=False)


def get_broker_config() -> BrokerConfig:
    return BrokerConfig(
        signing_key=os.getenv("BROKER_SIGNING_KEY", os.getenv("SECRET_KEY", "")),
        algorithm=os.getenv("ALGORITHM", "HS256"),
        default_ttl_seconds=int(os.getenv("BROKER_DEFAULT_TTL", "300")),
        max_ttl_seconds=int(os.getenv("BROKER_MAX_TTL", "3600")),
    )


# Vault resolver hook — replace with an OpenBao/Vaultwarden-backed resolver in
# deployment. Defaults to an empty in-memory vault so an unconfigured broker
# fails closed (redeem of a secret_ref yields a non-disclosing denial).
_vault_singleton: Optional[SecretResolver] = None


def get_vault() -> SecretResolver:
    global _vault_singleton
    if _vault_singleton is None:
        _vault_singleton = InMemoryVault()
    return _vault_singleton


def set_vault(resolver: SecretResolver) -> None:
    global _vault_singleton
    _vault_singleton = resolver


def new_session() -> Session:
    return _session_factory()()


def build_service(db: Session) -> BrokerService:
    return BrokerService(db, config=get_broker_config(), vault=get_vault())


def transport_from_headers(headers) -> TransportContext:
    """Build a TransportContext from gateway-verified headers only.

    ``headers`` is any case-insensitive mapping (FastAPI ``request.headers``).
    The asserted identity (``X-Asserted-Identity``) is captured for audit but
    never authorizes anything.
    """
    repo = headers.get("x-verified-repo")
    spiffe = headers.get("x-verified-spiffe")
    asserted = headers.get("x-asserted-identity")
    authed: Optional[TransportIdentity] = None
    if repo:
        authed = TransportIdentity(principal=f"repo:{repo}", method="oidc")
    elif spiffe:
        authed = TransportIdentity(principal=spiffe, method="mtls")
    return TransportContext(authenticated=authed, asserted_identity=asserted)
