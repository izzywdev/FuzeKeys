"""
MCP tool surface for the broker: ``keys.grant`` / ``keys.redeem`` /
``keys.mint_token`` / ``keys.revoke``.

These are thin, DETERMINISTIC wrappers over ``BrokerService`` for orchestrating
agents that call FuzeKeys directly over MCP. They do NOT contain policy logic of
their own — all authz/lifecycle lives in the core service.

SECURITY: the transport identity for redeem/mint_token comes from the MCP
session's authenticated principal (``TransportContext.authenticated``), which the
MCP server sets from the verified bearer/OIDC/mTLS credential — NEVER from a tool
argument. A tool argument may carry an *asserted* identity for audit only.

Return shapes are JSON-serializable dicts. Denials surface the generic
``BrokerDenied.PUBLIC_MESSAGE`` — tools never leak why.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from .errors import ApprovalRequired, BrokerDenied
from .identity import TransportContext, TransportIdentity
from .service import BrokerService


def keys_grant(
    service: BrokerService,
    *,
    grantor: TransportIdentity,
    redeemer_identity: str,
    scope: Dict[str, Any],
    ttl_seconds: Optional[int] = None,
    secret_ref: Optional[str] = None,
    operation: Optional[str] = None,
    single_use: bool = True,
    sensitivity: str = "medium",
) -> Dict[str, Any]:
    """MCP ``keys.grant`` — returns an opaque handle, never secret material."""
    res = service.grant(
        grantor=grantor,
        redeemer_identity=redeemer_identity,
        scope=scope,
        ttl_seconds=ttl_seconds,
        secret_ref=secret_ref,
        operation=operation,
        single_use=single_use,
        sensitivity=sensitivity,
    )
    return {
        "grant_id": res.grant_id,
        "grant_handle": res.handle,
        "expires_at": res.expires_at.isoformat(),
        "sensitivity": res.sensitivity,
    }


def keys_redeem(
    service: BrokerService,
    *,
    ctx: TransportContext,
    grant_handle: str,
) -> Dict[str, Any]:
    """MCP ``keys.redeem`` — releases a short-lived derived credential or defers."""
    try:
        res = service.redeem(ctx=ctx, handle=grant_handle)
    except ApprovalRequired as ar:
        return {
            "status": "approval_required",
            "request_id": ar.request_id,
            "expires_at": ar.expires_at.isoformat() if ar.expires_at else None,
        }
    except BrokerDenied as denied:
        return {"status": "denied", "message": denied.public_message}
    return {
        "status": "released",
        "kind": res.kind,
        "credential": res.credential,
        "expires_at": res.expires_at.isoformat(),
        "scope": res.scope,
    }


def keys_mint_token(
    service: BrokerService,
    *,
    ctx: TransportContext,
    audience: str,
    scope: str,
    ttl_seconds: Optional[int] = None,
) -> Dict[str, Any]:
    """MCP ``keys.mint_token`` — RFC 8693 token exchange."""
    try:
        token = service.mint_token(
            ctx=ctx, audience=audience, scope=scope, ttl_seconds=ttl_seconds
        )
    except BrokerDenied as denied:
        return {"status": "denied", "message": denied.public_message}
    return {
        "status": "issued",
        "access_token": token.access_token,
        "issued_token_type": token.issued_token_type,
        "token_type": token.token_type,
        "expires_in": token.expires_in,
        "scope": token.scope,
    }


def keys_revoke(
    service: BrokerService, *, grant_id: str, reason: str = "revoked"
) -> Dict[str, Any]:
    """MCP ``keys.revoke`` — instant, idempotent, non-disclosing."""
    service.revoke(grant_id=grant_id, reason=reason)
    return {"status": "revoked", "grant_id": grant_id}


# MCP tool descriptors — consumed by the FuzeKeys MCP server to register tools.
# Kept declarative so the server wiring stays in the existing MCP transport layer.
MCP_TOOL_SPECS = [
    {
        "name": "keys.grant",
        "description": "Issue an opaque, single-use, TTL-bound grant handle bound to a "
        "redeemer transport identity. Returns NO secret material.",
    },
    {
        "name": "keys.redeem",
        "description": "Redeem a grant handle as your authenticated transport identity; "
        "returns a short-lived derived credential (never the root secret).",
    },
    {
        "name": "keys.mint_token",
        "description": "RFC 8693 token exchange: exchange your identity token for a "
        "scoped, short-TTL downstream token.",
    },
    {
        "name": "keys.revoke",
        "description": "Instantly revoke a grant by id. Idempotent and non-disclosing.",
    },
]
