"""
FuzeKeys secret-broker — safe agent-to-agent secret exchange.

Doctrine (best -> fallback):
  1. Capability delegation (zero exchange) — grant an ``operation``; B does it.
  2. Secretless handoff — a non-secret grant handle travels; each agent redeems
     against FuzeKeys with its OWN authenticated transport identity.
  3. On redemption, release a short-lived DERIVED credential, never the root.

Public surface:
  - BrokerService (deterministic core): grant / redeem / mint_token / revoke
  - macaroons (attenuable capability handles)
  - envelope (KMS-style wrap-unwrap to a recipient public key)
  - derived (dynamic secrets + RFC 8693 token exchange)
"""
from .errors import ApprovalRequired, BrokerConfigError, BrokerDenied
from .identity import (
    TransportContext,
    TransportIdentity,
    resolve_transport_identity,
    transport_from_mtls,
    transport_from_oidc,
)
from .service import BrokerConfig, BrokerService, GrantResult, RedeemResult
from .vault import InMemoryVault, SecretResolver

__all__ = [
    "ApprovalRequired",
    "BrokerConfigError",
    "BrokerDenied",
    "TransportContext",
    "TransportIdentity",
    "resolve_transport_identity",
    "transport_from_mtls",
    "transport_from_oidc",
    "BrokerConfig",
    "BrokerService",
    "GrantResult",
    "RedeemResult",
    "InMemoryVault",
    "SecretResolver",
]
