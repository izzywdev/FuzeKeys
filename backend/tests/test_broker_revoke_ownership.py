"""Public grant handles cannot revoke another verified workload's SQL row."""

import hashlib
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient
from fuzefront_service_auth import TokenVerificationError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.broker import (
    BrokerConfig,
    BrokerService,
    InMemoryVault,
    TransportIdentity,
    runtime,
)
from app.database import Base
from app.main import app
from app.models.grant import Grant
from app.security import fuzefront_auth


@pytest.fixture
def broker_owner(monkeypatch):
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    cfg = BrokerConfig(
        signing_key=hashlib.sha256(b"broker-revoke-test-fixture").hexdigest()
    )
    owner = TransportIdentity(principal="service:owner", method="agent-token")
    with factory() as db:
        service = BrokerService(db, config=cfg, vault=InMemoryVault())
        grant = service.grant(
            grantor=owner,
            redeemer_identity="service:reader",
            scope={},
            operation="read_metadata",
        )
        grant_id = grant.grant_id
    session_hook = Mock(side_effect=factory)
    monkeypatch.setattr(runtime, "new_session", session_hook)
    monkeypatch.setattr(
        runtime,
        "build_service",
        lambda db: BrokerService(db, config=cfg, vault=InMemoryVault()),
    )
    verifier = Mock()
    verifier.verify_machine_token.return_value = fuzefront_auth.Identity(
        subject="service:owner",
        scopes=frozenset(),
        token_kind="fuze-workload",
        audience="service:fuzekeys",
    )
    monkeypatch.setattr(fuzefront_auth, "_verifier", lambda: verifier)
    client = TestClient(app, base_url="http://localhost")
    try:
        yield factory, client, grant_id, verifier, session_hook
    finally:
        client.close()
        engine.dispose()


@pytest.mark.parametrize(
    "proof",
    ["missing", "forged-headers", "invalid-token", "delegated-token", "wrong-audience"],
)
def test_revoke_denies_unverified_proofs_before_database(broker_owner, proof):
    factory, client, grant_id, verifier, session_hook = broker_owner
    headers = {}
    if proof == "forged-headers":
        headers = {
            "X-Verified-Repo": "owner",
            "X-Verified-Spiffe": "service:owner",
            "X-Asserted-Identity": "service:owner",
        }
    elif proof == "invalid-token":
        headers = {"Authorization": "Bearer invalid"}
        verifier.verify_machine_token.side_effect = TokenVerificationError("inactive")
    elif proof == "delegated-token":
        headers = {"Authorization": "Bearer delegation"}
        verifier.verify_machine_token.return_value = fuzefront_auth.Identity(
            subject="service:owner", scopes=frozenset(), token_kind="fuze-delegation"
        )
    elif proof == "wrong-audience":
        headers = {"Authorization": "Bearer other-target"}
        verifier.verify_machine_token.return_value = fuzefront_auth.Identity(
            subject="service:owner",
            scopes=frozenset(),
            token_kind="fuze-workload",
            audience="service:another",
        )
    response = client.post(
        "/api/v1/broker/revoke", headers=headers, json={"grant_id": grant_id}
    )
    assert response.status_code == (
        403 if proof in {"delegated-token", "wrong-audience"} else 401
    )
    session_hook.assert_not_called()
    with factory() as db:
        assert (
            db.query(Grant).filter(Grant.grant_id == grant_id).one().revoked_at is None
        )


def test_verified_foreign_and_missing_grants_share_noop_owner_can_revoke(broker_owner):
    factory, client, grant_id, verifier, session_hook = broker_owner
    verifier.verify_machine_token.return_value = fuzefront_auth.Identity(
        subject="service:foreign",
        scopes=frozenset(),
        token_kind="fuze-workload",
        audience="service:fuzekeys",
    )
    headers = {"Authorization": "Bearer verified"}
    foreign = client.post(
        "/api/v1/broker/revoke", headers=headers, json={"grant_id": grant_id}
    )
    missing = client.post(
        "/api/v1/broker/revoke", headers=headers, json={"grant_id": "missing"}
    )
    assert foreign.status_code == missing.status_code == 200
    assert foreign.json()["status"] == missing.json()["status"] == "revoked"
    with factory() as db:
        assert (
            db.query(Grant).filter(Grant.grant_id == grant_id).one().revoked_at is None
        )
    verifier.verify_machine_token.return_value = fuzefront_auth.Identity(
        subject="service:owner",
        scopes=frozenset(),
        token_kind="fuze-workload",
        audience="service:fuzekeys",
    )
    response = client.post(
        "/api/v1/broker/revoke", headers=headers, json={"grant_id": grant_id}
    )
    assert response.status_code == 200
    with factory() as db:
        assert (
            db.query(Grant).filter(Grant.grant_id == grant_id).one().revoked_at
            is not None
        )
    assert (
        client.post(
            "/api/v1/broker/revoke", headers=headers, json={"grant_id": grant_id}
        ).status_code
        == 200
    )


def test_unmapped_legacy_principal_is_not_rewritten_to_current_workload(broker_owner):
    factory, client, grant_id, verifier, session_hook = broker_owner
    with factory() as db:
        row = db.query(Grant).filter(Grant.grant_id == grant_id).one()
        row.grantor_identity = "repo:izzywdev/legacy-service"
        db.commit()
    response = client.post(
        "/api/v1/broker/revoke",
        headers={"Authorization": "Bearer verified"},
        json={"grant_id": grant_id},
    )
    assert response.status_code == 200
    with factory() as db:
        row = db.query(Grant).filter(Grant.grant_id == grant_id).one()
        assert row.revoked_at is None
        assert row.grantor_identity == "repo:izzywdev/legacy-service"
