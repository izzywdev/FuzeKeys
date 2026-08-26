"""
Broker grant model — the non-secret record backing a secretless agent-to-agent
handoff (design hierarchy tier 2 in docs/superpowers/specs/...-mcp-design.md and
the FuzeKeys secret-broker doctrine).

A `Grant` row NEVER stores secret material. It stores:
  - an opaque public ``grant_id`` (the caller sees this, plus a macaroon handle),
  - the **bound redeemer transport identity** (an OIDC ``repo`` claim / SPIFFE id /
    mTLS subject — NOT a caller-asserted value; see broker/identity.py),
  - a *reference* to the secret (``secret_ref``) or a capability ``operation`` — the
    real credential stays in the vault (OpenBao/Vaultwarden) and is only ever
    released as a short-lived DERIVED credential on redeem,
  - the macaroon root verification key (server-side only; a signing key, not the
    user's secret),
  - lifecycle: ttl/expiry, single-use, redemption count, revocation.

Standards grounding:
  - Macaroons (Birgisson et al., 2014) for attenuable, verifiable capability handles.
  - HashiCorp/OpenBao dynamic secrets + response-wrapping: the vault is the system
    of record; the broker releases short-lived derived creds, never the root.
"""
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
    Text,
)
from sqlalchemy.sql import func

from app.database import Base


class Grant(Base):
    """A single secretless grant: bound to ONE redeemer transport identity."""

    __tablename__ = "broker_grants"

    id = Column(Integer, primary_key=True, index=True)

    # Opaque, server-issued public identifier. Carries no secret material and is
    # also the macaroon identifier used to look the root key up at redeem time.
    grant_id = Column(String(64), nullable=False, unique=True, index=True)

    # Fingerprint (sha256) of the opaque handle returned to the caller, so we can
    # match a presented handle without ever storing the handle itself.
    handle_fingerprint = Column(String(128), nullable=False, index=True)

    # The authenticated transport identity that CREATED the grant (grantor B) and
    # the authenticated transport identity permitted to redeem it (redeemer A).
    grantor_identity = Column(String(255), nullable=False, index=True)
    redeemer_identity = Column(String(255), nullable=False, index=True)

    # Exactly one of these is set. ``secret_ref`` = a handle to a vault secret the
    # agent must genuinely hold; ``operation`` = a capability-delegation verb (tier
    # 1, preferred) where B DOES the thing and never reveals its secret.
    secret_ref = Column(String(300), nullable=True)
    operation = Column(String(120), nullable=True)

    # Attenuable scope (JSON) + sensitivity class. HIGH => human approval required
    # before release (reach_human / digital-persona), mirroring the approval plane.
    scope = Column(Text, nullable=False, default="{}")
    sensitivity = Column(
        String(20), nullable=False, default="medium"
    )  # low|medium|high

    ttl_seconds = Column(Integer, nullable=False)
    single_use = Column(Boolean, nullable=False, default=True)

    # Macaroon root verification key — server-side ONLY, never leaves the broker.
    root_key = Column(LargeBinary, nullable=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    expires_at = Column(DateTime(timezone=True), nullable=False, index=True)

    redemption_count = Column(Integer, nullable=False, default=0)
    redeemed_at = Column(DateTime(timezone=True), nullable=True)
    redeemed_by = Column(String(255), nullable=True)

    revoked_at = Column(DateTime(timezone=True), nullable=True)
    revoked_reason = Column(String(255), nullable=True)

    # Link to a pending human approval when sensitivity == high.
    approval_request_id = Column(
        Integer, ForeignKey("approval_requests.id"), nullable=True
    )
