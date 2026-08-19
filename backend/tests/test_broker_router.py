"""
HTTP-surface integration tests for the broker router.

Exercises grant -> redeem -> revoke over FastAPI, proving:
  - transport identity is taken from gateway-verified headers (X-Verified-Repo),
    NOT the request body;
  - a body-asserted identity cannot redeem a grant bound to someone else;
  - the HTTP surface never returns the root secret.

The router's sync session + vault are redirected to an in-memory SQLite DB.
"""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.broker import BrokerConfig, InMemoryVault, runtime
from app.database import Base
from app.routers import broker as broker_router

ROOT = b"root-secret-http-never-leak"
REF = "openbao:kv/http"


@pytest.fixture()
def client(monkeypatch):
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False)

    monkeypatch.setattr(runtime, "new_session", lambda: Session())
    monkeypatch.setattr(
        runtime,
        "get_broker_config",
        lambda: BrokerConfig(signing_key="strong-http-signing-key-abcdefgh"),
    )
    runtime.set_vault(InMemoryVault({REF: ROOT}))

    app = FastAPI()
    app.include_router(broker_router.router)
    return TestClient(app)


AGENT_A = "izzywdev/FuzeAgent"
AGENT_B = "izzywdev/FuzeBI"


def test_grant_redeem_over_http(client):
    g = client.post(
        "/api/v1/broker/grant",
        headers={"X-Verified-Repo": AGENT_B},
        json={
            "redeemer_identity": f"repo:{AGENT_A}",
            "scope": {"action": "read"},
            "secret_ref": REF,
        },
    ).json()
    assert "grant_handle" in g and ROOT.decode() not in g["grant_handle"]

    r = client.post(
        "/api/v1/broker/redeem",
        headers={"X-Verified-Repo": AGENT_A},
        json={"grant_handle": g["grant_handle"]},
    ).json()
    assert r["status"] == "released"
    assert ROOT.decode() not in r["credential"]


def test_asserted_header_cannot_redeem_other_identity(client):
    g = client.post(
        "/api/v1/broker/grant",
        headers={"X-Verified-Repo": AGENT_B},
        json={"redeemer_identity": f"repo:{AGENT_A}", "scope": {}, "secret_ref": REF},
    ).json()
    # caller authenticates as B but ASSERTS it is A in the body-level header
    r = client.post(
        "/api/v1/broker/redeem",
        headers={"X-Verified-Repo": AGENT_B, "X-Asserted-Identity": f"repo:{AGENT_A}"},
        json={"grant_handle": g["grant_handle"]},
    ).json()
    assert r["status"] == "denied"
    assert r["message"] == "grant is not redeemable"


def test_unauthenticated_grant_denied(client):
    r = client.post(
        "/api/v1/broker/grant",
        json={"redeemer_identity": f"repo:{AGENT_A}", "scope": {}, "secret_ref": REF},
    ).json()
    assert r["status"] == "denied"


def test_mint_token_over_http(client):
    r = client.post(
        "/api/v1/broker/mint-token",
        headers={"X-Verified-Repo": AGENT_A},
        json={"audience": "FuzeBI", "scope": "read:x"},
    ).json()
    assert r["status"] == "issued"
    assert r["expires_in"] > 0
