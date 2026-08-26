"""
MCP tool-surface tests: keys.grant / keys.redeem / keys.mint_token / keys.revoke
return JSON-serializable dicts and never leak secret material or denial reasons.
"""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.models  # noqa: F401
from app.broker import (
    BrokerConfig,
    BrokerService,
    InMemoryVault,
    TransportContext,
    TransportIdentity,
    mcp_tools,
)
from app.database import Base

ROOT = b"root-secret-never-leak"
REF = "openbao:kv/x"
A = TransportIdentity(principal="repo:izzywdev/FuzeAgent", method="oidc")
B = TransportIdentity(principal="repo:izzywdev/FuzeBI", method="oidc")


@pytest.fixture()
def service():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    s = sessionmaker(bind=engine)()
    vault = InMemoryVault({REF: ROOT})
    cfg = BrokerConfig(signing_key="strong-signing-key-abcdefghijklmnop")
    return BrokerService(s, config=cfg, vault=vault)


def _ctx(authed, asserted=None):
    return TransportContext(authenticated=authed, asserted_identity=asserted)


def test_grant_then_redeem_flow(service):
    g = mcp_tools.keys_grant(
        service,
        grantor=B,
        redeemer_identity=A.principal,
        scope={"action": "read"},
        secret_ref=REF,
    )
    assert "grant_handle" in g and ROOT.decode() not in g["grant_handle"]
    r = mcp_tools.keys_redeem(service, ctx=_ctx(A), grant_handle=g["grant_handle"])
    assert r["status"] == "released"
    assert ROOT.decode() not in r["credential"]


def test_redeem_wrong_identity_returns_generic_denial(service):
    g = mcp_tools.keys_grant(
        service,
        grantor=B,
        redeemer_identity=A.principal,
        scope={},
        secret_ref=REF,
    )
    r = mcp_tools.keys_redeem(service, ctx=_ctx(B), grant_handle=g["grant_handle"])
    assert r["status"] == "denied"
    assert r["message"] == "grant is not redeemable"


def test_mint_token_tool(service):
    r = mcp_tools.keys_mint_token(
        service, ctx=_ctx(A), audience="FuzeBI", scope="read:x"
    )
    assert r["status"] == "issued"
    assert r["token_type"] == "Bearer"
    assert r["issued_token_type"].endswith("access_token")


def test_revoke_tool(service):
    g = mcp_tools.keys_grant(
        service,
        grantor=B,
        redeemer_identity=A.principal,
        scope={},
        secret_ref=REF,
    )
    out = mcp_tools.keys_revoke(service, grant_id=g["grant_id"])
    assert out["status"] == "revoked"
    r = mcp_tools.keys_redeem(service, ctx=_ctx(A), grant_handle=g["grant_handle"])
    assert r["status"] == "denied"


def test_high_sensitivity_returns_approval_required(service):
    g = mcp_tools.keys_grant(
        service,
        grantor=B,
        redeemer_identity=A.principal,
        scope={},
        secret_ref=REF,
        sensitivity="high",
    )
    r = mcp_tools.keys_redeem(service, ctx=_ctx(A), grant_handle=g["grant_handle"])
    assert r["status"] == "approval_required"
    assert "request_id" in r


def test_tool_specs_declared():
    names = {t["name"] for t in mcp_tools.MCP_TOOL_SPECS}
    assert names == {"keys.grant", "keys.redeem", "keys.mint_token", "keys.revoke"}
