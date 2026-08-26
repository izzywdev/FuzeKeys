"""
HTTP surface for the FuzeKeys secret-broker.

Deterministic REST endpoints that the MCP server and the A2A serving role sit on
top of. Sync path-operations (FastAPI runs them in a threadpool) drive the sync
BrokerService core.

Endpoints:
  POST /api/v1/broker/grant       -> opaque grant handle (no secret material)
  POST /api/v1/broker/redeem      -> derived credential | approval_required | denied
  POST /api/v1/broker/mint-token  -> RFC 8693 token exchange
  POST /api/v1/broker/revoke      -> revoke (idempotent, non-disclosing)

Transport identity is resolved from gateway-verified headers only (never the
body). See app/broker/runtime.py.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from app.broker import mcp_tools, runtime
from app.broker.errors import BrokerConfigError
from app.broker.identity import TransportIdentity

router = APIRouter(prefix="/api/v1/broker", tags=["Secret Broker"])


class GrantRequest(BaseModel):
    redeemer_identity: str = Field(
        ..., description="Bound transport identity that may redeem"
    )
    scope: Dict[str, Any] = Field(default_factory=dict)
    ttl_seconds: Optional[int] = Field(
        None, description="Clamped to the server maximum"
    )
    secret_ref: Optional[str] = None
    operation: Optional[str] = None
    single_use: bool = True
    sensitivity: str = "medium"


class RedeemRequest(BaseModel):
    grant_handle: str


class MintTokenRequest(BaseModel):
    audience: str
    scope: str
    ttl_seconds: Optional[int] = None


class RevokeRequest(BaseModel):
    grant_id: str
    reason: str = "revoked"


@router.post("/grant")
def grant(body: GrantRequest, request: Request):
    """Issue a grant. The grantor is the caller's authenticated transport identity."""
    ctx = runtime.transport_from_headers(request.headers)
    db = runtime.new_session()
    try:
        service = runtime.build_service(db)
        # Grantor must itself be an authenticated principal.
        if ctx.authenticated is None:
            return {"status": "denied", "message": "grant is not redeemable"}
        grantor: TransportIdentity = ctx.authenticated
        try:
            return mcp_tools.keys_grant(
                service,
                grantor=grantor,
                redeemer_identity=body.redeemer_identity,
                scope=body.scope,
                ttl_seconds=body.ttl_seconds,
                secret_ref=body.secret_ref,
                operation=body.operation,
                single_use=body.single_use,
                sensitivity=body.sensitivity,
            )
        except BrokerConfigError as exc:
            return {"status": "error", "message": str(exc)}
    finally:
        db.close()


@router.post("/redeem")
def redeem(body: RedeemRequest, request: Request):
    ctx = runtime.transport_from_headers(request.headers)
    db = runtime.new_session()
    try:
        service = runtime.build_service(db)
        return mcp_tools.keys_redeem(service, ctx=ctx, grant_handle=body.grant_handle)
    finally:
        db.close()


@router.post("/mint-token")
def mint_token(body: MintTokenRequest, request: Request):
    ctx = runtime.transport_from_headers(request.headers)
    db = runtime.new_session()
    try:
        service = runtime.build_service(db)
        return mcp_tools.keys_mint_token(
            service,
            ctx=ctx,
            audience=body.audience,
            scope=body.scope,
            ttl_seconds=body.ttl_seconds,
        )
    finally:
        db.close()


@router.post("/revoke")
def revoke(body: RevokeRequest, request: Request):
    db = runtime.new_session()
    try:
        service = runtime.build_service(db)
        return mcp_tools.keys_revoke(
            service, grant_id=body.grant_id, reason=body.reason
        )
    finally:
        db.close()
