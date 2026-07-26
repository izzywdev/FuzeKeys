"""
BrokerService — the deterministic core of the FuzeKeys secret-broker.

This is SECURITY INFRASTRUCTURE, not an LLM. Every decision here is deterministic
and auditable. It implements the doctrine's safe agent-to-agent secret exchange:

  grant()      -> opaque handle, NO secret material
  redeem()     -> authenticates the caller's TRANSPORT identity, verifies the
                  grant is bound to it / not expired / not used / not revoked /
                  policy-permitted, then releases a SHORT-LIVED DERIVED credential
                  (never the long-lived root). Non-disclosing on any failure.
  mint_token() -> RFC 8693 token exchange (the secretless ideal).
  revoke()     -> instant revocation.

Persistence is a synchronous SQLAlchemy ``Session`` so the core is trivially
unit-testable (matches the repo's existing model-test style) and can be driven
from FastAPI sync path-operations (run in a threadpool).
"""
from __future__ import annotations

import hashlib
import json
import os
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.models.grant import Grant
from app.models.approval import ApprovalRequest, AuditLog

from . import macaroons
from .derived import (
    DerivedCredential,
    ExchangedToken,
    derive_credential,
    mint_exchanged_token,
)
from .errors import ApprovalRequired, BrokerConfigError, BrokerDenied
from .identity import TransportContext, TransportIdentity, resolve_transport_identity
from .vault import SecretResolver

_INSECURE_SIGNING_KEYS = {
    "",
    "your-secret-key",
    "your-super-secret-key-here-change-this-in-production",
}


@dataclass(frozen=True)
class BrokerConfig:
    signing_key: str
    algorithm: str = "HS256"
    default_ttl_seconds: int = 300
    max_ttl_seconds: int = 3600
    issuer: str = "fuzekeys-broker"

    def require_signing_key(self) -> str:
        key = (self.signing_key or "").strip()
        if key in _INSECURE_SIGNING_KEYS:
            # Fail closed — never mint on a weak/absent key.
            raise BrokerConfigError("broker signing key is unset or insecure")
        return key


@dataclass(frozen=True)
class GrantResult:
    grant_id: str
    handle: str          # opaque macaroon, carries NO secret material
    expires_at: datetime
    sensitivity: str


@dataclass(frozen=True)
class RedeemResult:
    kind: str            # "derived_secret" | "operation_token"
    credential: str      # short-lived DERIVED material — NEVER the root
    expires_at: datetime
    scope: dict
    grant_id: str


def _clamp_scope_to_grant(effective: dict, authoritative: dict) -> dict:
    """Return the subset of ``effective`` that is within the grant's ``authoritative``
    scope — the released scope can never EXCEED what the grantor authorized.

    Iterating the authoritative ceiling guarantees the result is a subset of it:
      - a key only in ``effective`` (holder-injected) is dropped — it is not in the
        ceiling, so it can never be released;
      - a key the holder narrowed away (absent from ``effective``) stays dropped;
      - list values are intersected with the ceiling (⊆ authoritative);
      - a scalar the holder tried to change is clamped back to the grant's value.
    This is the deterministic guard behind macaroon attenuation (defense in depth).
    """
    clamped: dict = {}
    for key, auth_val in authoritative.items():
        if key not in effective:
            # holder narrowed by dropping the key -> honour the narrowing.
            continue
        eff_val = effective[key]
        if isinstance(auth_val, list) and isinstance(eff_val, list):
            clamped[key] = [x for x in auth_val if x in eff_val]
        elif eff_val == auth_val:
            clamped[key] = auth_val
        else:
            # holder tried to change a scalar -> clamp to the grant's own value.
            clamped[key] = auth_val
    return clamped


def _sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is not None and dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


class BrokerService:
    def __init__(
        self,
        db: Session,
        *,
        config: BrokerConfig,
        vault: SecretResolver,
    ) -> None:
        self.db = db
        self.config = config
        self.vault = vault

    # ---- audit ---------------------------------------------------------
    def _audit(
        self,
        *,
        resource_ref: str,
        decision: str,
        redeemer: Optional[str] = None,
    ) -> None:
        # AuditLog stores NO secret value — only who/what/when/decision.
        entry = AuditLog(
            agent_id=None,
            on_behalf_user_id=None,
            identity_id=None,
            resource_ref=(resource_ref if redeemer is None else f"{resource_ref} redeemer={redeemer}")[:300],
            decision=decision[:40],
        )
        self.db.add(entry)

    # ---- grant ---------------------------------------------------------
    def grant(
        self,
        *,
        grantor: TransportIdentity,
        redeemer_identity: str,
        scope: dict,
        ttl_seconds: Optional[int] = None,
        secret_ref: Optional[str] = None,
        operation: Optional[str] = None,
        single_use: bool = True,
        sensitivity: str = "medium",
    ) -> GrantResult:
        if bool(secret_ref) == bool(operation):
            raise BrokerConfigError("exactly one of secret_ref or operation is required")
        if not redeemer_identity or not redeemer_identity.strip():
            raise BrokerConfigError("redeemer_identity is required")
        if sensitivity not in ("low", "medium", "high"):
            raise BrokerConfigError("sensitivity must be low|medium|high")

        # TTL: apply default + clamp to the server-side maximum.
        ttl = ttl_seconds or self.config.default_ttl_seconds
        ttl = max(1, min(int(ttl), self.config.max_ttl_seconds))

        grant_id = uuid.uuid4().hex
        root_key = os.urandom(32)
        now = _now()
        expires_at = now + timedelta(seconds=ttl)

        handle = macaroons.mint_handle(
            root_key=root_key,
            grant_id=grant_id,
            redeemer=redeemer_identity,
            expires_at=expires_at,
            scope=scope,
            single_use=single_use,
        )

        row = Grant(
            grant_id=grant_id,
            handle_fingerprint=_sha256_hex(handle),
            grantor_identity=grantor.principal,
            redeemer_identity=redeemer_identity,
            secret_ref=secret_ref,
            operation=operation,
            scope=json.dumps(scope, sort_keys=True),
            sensitivity=sensitivity,
            ttl_seconds=ttl,
            single_use=single_use,
            root_key=root_key,
            expires_at=expires_at,
        )
        self.db.add(row)
        self._audit(
            resource_ref=f"grant:{grant_id} ref={secret_ref or operation}",
            decision="grant_created",
        )
        self.db.commit()
        return GrantResult(
            grant_id=grant_id, handle=handle, expires_at=expires_at, sensitivity=sensitivity
        )

    # ---- redeem --------------------------------------------------------
    def redeem(self, *, ctx: TransportContext, handle: str) -> RedeemResult:
        # 1) Authenticate the caller's TRANSPORT identity. Asserted identity is
        #    never trusted; resolve_transport_identity fails closed without a
        #    verified principal.
        caller = resolve_transport_identity(ctx)

        # 2) Recover the grant id from the macaroon and load the row. Any lookup
        #    miss yields the SAME non-disclosing denial as an authz failure.
        grant_id = self._grant_id_from_handle(handle)
        row = self._load_grant_or_deny(grant_id)

        # 3) Cryptographically verify the handle against the stored root key and
        #    all caveats (binds to this caller + not expired-by-caveat).
        try:
            bounds = macaroons.verify_handle(
                handle=handle,
                root_key=row.root_key,
                grant_id=grant_id,
                caller=caller.principal,
            )
        except Exception:
            self._audit(resource_ref=f"grant:{grant_id}", decision="denied", redeemer=caller.principal)
            self.db.commit()
            raise BrokerDenied("macaroon verification failed")

        # 4) Defense-in-depth DB checks (independent of the caveats). NB: we do NOT
        #    gate on handle_fingerprint here — a legitimately ATTENUATED handle has
        #    a different serialization; the macaroon signature (verified above) is
        #    the integrity guarantee. The fingerprint column is for lookup/audit.
        if row.redeemer_identity != caller.principal:
            self._deny(grant_id, caller.principal, "redeemer mismatch")
        if row.revoked_at is not None:
            self._deny(grant_id, caller.principal, "revoked")
        if _now() > _aware(row.expires_at):
            self._deny(grant_id, caller.principal, "expired")
        if row.single_use and row.redemption_count >= 1:
            self._deny(grant_id, caller.principal, "already redeemed (single-use)")

        # 5) Asserted-vs-authenticated mismatch is an audited anomaly but we ALWAYS
        #    authorize on the authenticated identity, never the asserted one.
        if ctx.asserted_identity and ctx.asserted_identity != caller.principal:
            self._audit(
                resource_ref=f"grant:{grant_id} asserted={ctx.asserted_identity}",
                decision="identity_assertion_ignored",
                redeemer=caller.principal,
            )

        # 6) High-sensitivity => human approval gate (reach_human / persona).
        if row.sensitivity == "high":
            self._enforce_approval(row, caller.principal)

        # Effective scope honours macaroon attenuation: an A->B->C hop that added a
        # narrowing `scope <=` caveat gets the INTERSECTED (narrowed) scope, never
        # the original grant's wider scope.
        authoritative_scope = json.loads(row.scope or "{}")
        effective_scope = bounds.scope if bounds.scope is not None else authoritative_scope
        # DEFENSE IN DEPTH (privilege-escalation guard): regardless of what caveats
        # were appended, clamp the released scope to a SUBSET of the grantor's
        # original scope. A holder can never redeem more than was granted, even if
        # macaroon-layer attenuation were bypassed. Applied to BOTH release paths.
        scope = _clamp_scope_to_grant(effective_scope, authoritative_scope)

        # 7) Release. NEVER the root: either a derived secret or an operation token.
        if row.secret_ref:
            root = self.vault.load_root(row.secret_ref)
            if root is None:
                # Non-disclosing: don't reveal whether the ref exists.
                self._deny(grant_id, caller.principal, "secret_ref unresolved")
            derived: DerivedCredential = derive_credential(
                root_secret=root,
                secret_ref=row.secret_ref,
                redeemer=caller.principal,
                scope=json.dumps(scope, sort_keys=True),
                ttl_seconds=row.ttl_seconds,
            )
            kind, credential, expires_at = "derived_secret", derived.value, derived.expires_at
        else:
            # Capability delegation / operation grant: mint a scoped action token.
            token = mint_exchanged_token(
                signing_key=self.config.require_signing_key(),
                algorithm=self.config.algorithm,
                subject_principal=caller.principal,
                audience=row.operation or "operation",
                scope=json.dumps(scope, sort_keys=True),
                ttl_seconds=row.ttl_seconds,
                issuer=self.config.issuer,
            )
            kind, credential, expires_at = "operation_token", token.access_token, _now() + timedelta(seconds=token.expires_in)

        row.redemption_count += 1
        row.redeemed_at = _now()
        row.redeemed_by = caller.principal
        self._audit(
            resource_ref=f"grant:{grant_id} ref={row.secret_ref or row.operation}",
            decision="approved" if row.sensitivity == "high" else "auto_release",
            redeemer=caller.principal,
        )
        self.db.commit()
        return RedeemResult(
            kind=kind, credential=credential, expires_at=expires_at, scope=scope, grant_id=grant_id
        )

    # ---- mint_token (RFC 8693) ----------------------------------------
    def mint_token(
        self,
        *,
        ctx: TransportContext,
        audience: str,
        scope: str,
        ttl_seconds: Optional[int] = None,
    ) -> ExchangedToken:
        caller = resolve_transport_identity(ctx)
        ttl = ttl_seconds or self.config.default_ttl_seconds
        ttl = max(1, min(int(ttl), self.config.max_ttl_seconds))
        token = mint_exchanged_token(
            signing_key=self.config.require_signing_key(),
            algorithm=self.config.algorithm,
            subject_principal=caller.principal,
            audience=audience,
            scope=scope,
            ttl_seconds=ttl,
            issuer=self.config.issuer,
        )
        self._audit(
            resource_ref=f"token_exchange aud={audience} scope={scope}",
            decision="token_minted",
            redeemer=caller.principal,
        )
        self.db.commit()
        return token

    # ---- revoke --------------------------------------------------------
    def revoke(self, *, grant_id: str, reason: str = "revoked") -> bool:
        row = (
            self.db.query(Grant).filter(Grant.grant_id == grant_id).one_or_none()
        )
        if row is None:
            # Idempotent + non-disclosing: report the same result either way.
            self._audit(resource_ref=f"grant:{grant_id}", decision="revoke_noop")
            self.db.commit()
            return True
        if row.revoked_at is None:
            row.revoked_at = _now()
            row.revoked_reason = reason[:255]
        self._audit(resource_ref=f"grant:{grant_id}", decision="revoked")
        self.db.commit()
        return True

    # ---- helpers -------------------------------------------------------
    def _grant_id_from_handle(self, handle: str) -> str:
        try:
            m = macaroons.Macaroon.deserialize(handle)
            return m.identifier_bytes.decode("utf-8") if hasattr(m, "identifier_bytes") else str(m.identifier)
        except Exception:
            # Malformed handle -> generic denial.
            raise BrokerDenied("malformed grant handle")

    def _load_grant_or_deny(self, grant_id: str) -> Grant:
        row = self.db.query(Grant).filter(Grant.grant_id == grant_id).one_or_none()
        if row is None:
            raise BrokerDenied("no such grant")
        return row

    def _deny(self, grant_id: str, caller: str, reason: str) -> "None":
        self._audit(resource_ref=f"grant:{grant_id}", decision="denied", redeemer=caller)
        self.db.commit()
        raise BrokerDenied(reason)

    def _enforce_approval(self, row: Grant, caller: str) -> None:
        req = None
        if row.approval_request_id is not None:
            req = self.db.query(ApprovalRequest).filter(
                ApprovalRequest.id == row.approval_request_id
            ).one_or_none()
        if req is None:
            # Create a pending approval and defer (reach_human path).
            req = ApprovalRequest(
                agent_id=0,
                resource_ref=f"grant:{row.grant_id}",
                status="pending",
                expires_at=_aware(row.expires_at),
            )
            self.db.add(req)
            self.db.flush()
            row.approval_request_id = req.id
            self._audit(resource_ref=f"grant:{row.grant_id}", decision="approval_required", redeemer=caller)
            self.db.commit()
            raise ApprovalRequired(request_id=req.id, expires_at=_aware(row.expires_at))
        if req.status == "approved":
            return
        if req.status in ("denied", "expired"):
            self._deny(row.grant_id, caller, f"approval {req.status}")
        # still pending
        self._audit(resource_ref=f"grant:{row.grant_id}", decision="approval_pending", redeemer=caller)
        self.db.commit()
        raise ApprovalRequired(request_id=req.id, expires_at=_aware(row.expires_at))
