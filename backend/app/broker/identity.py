"""
Transport identity resolution for the broker.

DOCTRINE (mirrors A2A authz.md §1 and SPIFFE workload-identity):
the broker authenticates the caller as its **transport identity** — the identity
proven by the *channel*, not one the caller *asserts* in the request body.

Accepted transport proofs (verified upstream by FuzeKeys' existing identity plane):
  - an **OIDC token** whose ``repo`` claim identifies the calling workload
    (GitHub Actions OIDC / FuzeOne A2A), e.g. ``repo:izzywdev/FuzeAgent`` ;
  - an **mTLS / SPIFFE** peer certificate, e.g. ``spiffe://fuzeone/agent/FuzeAgent``
    or an X.509 subject CN.

A caller-**asserted** identity (a field in the JSON/MCP arg / prompt) is captured
only so it can be checked against the authenticated one for audit/anomaly — it is
NEVER used to authorize a release. If asserted != authenticated we still authorize
on the authenticated value (and the mismatch is audited).

References:
  - SPIFFE/SPIRE workload identity (spiffe.io) — identity is attested, not claimed.
  - RFC 8693 §1.1 — the subject is the authenticated token, not request content.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .errors import BrokerDenied


@dataclass(frozen=True)
class TransportIdentity:
    """The authenticated principal of the calling workload."""

    #: canonical principal string, e.g. "repo:izzywdev/FuzeAgent"
    principal: str
    #: how it was proven: "oidc" | "mtls" | "agent-token"
    method: str

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.principal


@dataclass(frozen=True)
class TransportContext:
    """Everything the broker knows about a caller for one request.

    ``authenticated`` is set ONLY by the trusted auth layer after it has verified
    the transport proof. ``asserted_identity`` is whatever the caller put in the
    payload and is untrusted by construction.
    """

    authenticated: Optional[TransportIdentity]
    asserted_identity: Optional[str] = None


def transport_from_oidc(verified_claims: dict) -> TransportIdentity:
    """Build a transport identity from ALREADY-VERIFIED OIDC claims.

    The signature/issuer/audience verification is the identity plane's job; this
    only projects the trusted ``repo`` (or ``sub``) claim into a principal.
    """
    repo = verified_claims.get("repo") or verified_claims.get("sub")
    if not repo:
        raise BrokerDenied("oidc token carries no repo/sub claim")
    return TransportIdentity(principal=f"repo:{repo}", method="oidc")


def transport_from_mtls(subject: str) -> TransportIdentity:
    """Build a transport identity from a verified mTLS/SPIFFE peer subject."""
    if not subject or not subject.strip():
        raise BrokerDenied("empty mTLS subject")
    return TransportIdentity(principal=subject.strip(), method="mtls")


def resolve_transport_identity(ctx: TransportContext) -> TransportIdentity:
    """Return the authenticated identity or fail closed.

    SECURITY: this NEVER falls back to ``ctx.asserted_identity``. If the channel
    did not authenticate the caller, we deny — an asserted identity alone can
    never authorize anything.
    """
    if ctx.authenticated is None or not ctx.authenticated.principal:
        raise BrokerDenied("no authenticated transport identity on request")
    return ctx.authenticated
