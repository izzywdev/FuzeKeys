"""
Broker security-invariant tests.

These import ONLY the broker + model modules (never app.main, which has a
pre-existing cv2 import break) and run against in-memory SQLite, matching
test_identity_vault_models.py.

Invariants proven (the doctrine's non-negotiables):
  1. a grant is redeemable ONLY by the bound transport identity;
  2. TTL is enforced (expired grant fails);
  3. single-use is enforced (second redeem fails);
  4. a revoked grant fails;
  5. the ROOT secret is NEVER returned — only a derived credential;
  6. a caller-ASSERTED identity is ignored (authz is on the authenticated one);
  7. macaroon attenuation can only NARROW scope, never widen;
  8. denials are non-disclosing (same message for missing vs unauthorized);
  9. TTL is clamped to the server maximum;
 10. mint_token performs an RFC 8693 exchange bound to the authenticated identity.
"""
import json
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
import app.models  # noqa: F401  registers every table on Base.metadata
from app.models.grant import Grant

from app.broker import (
    BrokerConfig,
    BrokerDenied,
    BrokerService,
    InMemoryVault,
    TransportContext,
    TransportIdentity,
    transport_from_oidc,
)
from app.broker import macaroons
from app.broker.errors import ApprovalRequired
from app.broker.service import _sha256_hex


ROOT_SECRET = b"super-long-lived-root-token-DO-NOT-LEAK"
SECRET_REF = "openbao:kv/identities/1/github/ci-token"

AGENT_A = TransportIdentity(principal="repo:izzywdev/FuzeAgent", method="oidc")
AGENT_B = TransportIdentity(principal="repo:izzywdev/FuzeBI", method="oidc")


@pytest.fixture()
def db():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    s = Session()
    yield s
    s.close()


@pytest.fixture()
def vault():
    v = InMemoryVault()
    v.put(SECRET_REF, ROOT_SECRET)
    return v


@pytest.fixture()
def service(db, vault):
    cfg = BrokerConfig(signing_key="a-strong-broker-signing-key-1234567890", max_ttl_seconds=3600)
    return BrokerService(db, config=cfg, vault=vault)


def _ctx(authed, asserted=None):
    return TransportContext(authenticated=authed, asserted_identity=asserted)


def _grant(service, **overrides):
    kwargs = dict(
        grantor=AGENT_B,
        redeemer_identity=AGENT_A.principal,
        scope={"repos": ["FuzeAgent"], "action": "read"},
        ttl_seconds=300,
        secret_ref=SECRET_REF,
        single_use=True,
        sensitivity="medium",
    )
    kwargs.update(overrides)
    return service.grant(**kwargs)


# 1 -----------------------------------------------------------------------
def test_grant_returns_opaque_handle_with_no_secret_material(service):
    g = _grant(service)
    assert g.grant_id
    assert ROOT_SECRET.decode() not in g.handle
    assert "super-long-lived-root" not in g.handle
    # handle is a macaroon (carries caveats/policy, not secrets)
    assert macaroons.Macaroon.deserialize(g.handle).identifier == g.grant_id


def test_grant_is_redeemable_by_bound_identity(service):
    g = _grant(service)
    res = service.redeem(ctx=_ctx(AGENT_A), handle=g.handle)
    assert res.kind == "derived_secret"
    assert res.credential


# 1 (negative) ------------------------------------------------------------
def test_redeem_by_wrong_identity_is_denied(service):
    g = _grant(service)
    with pytest.raises(BrokerDenied):
        service.redeem(ctx=_ctx(AGENT_B), handle=g.handle)


def test_redeem_without_authenticated_identity_is_denied(service):
    g = _grant(service)
    # asserted-only context (no authenticated principal) must fail closed
    with pytest.raises(BrokerDenied):
        service.redeem(ctx=_ctx(None, asserted=AGENT_A.principal), handle=g.handle)


# 2 -----------------------------------------------------------------------
def test_ttl_enforced_expired_grant_fails(service, db):
    g = _grant(service, ttl_seconds=1)
    row = db.query(Grant).filter(Grant.grant_id == g.grant_id).one()
    row.expires_at = datetime.now(timezone.utc) - timedelta(seconds=5)
    db.commit()
    with pytest.raises(BrokerDenied):
        service.redeem(ctx=_ctx(AGENT_A), handle=g.handle)


def test_ttl_clamped_to_server_max(service, db):
    g = _grant(service, ttl_seconds=999999)
    row = db.query(Grant).filter(Grant.grant_id == g.grant_id).one()
    assert row.ttl_seconds == 3600  # clamped to max


# 3 -----------------------------------------------------------------------
def test_single_use_second_redeem_fails(service):
    g = _grant(service, single_use=True)
    first = service.redeem(ctx=_ctx(AGENT_A), handle=g.handle)
    assert first.credential
    with pytest.raises(BrokerDenied):
        service.redeem(ctx=_ctx(AGENT_A), handle=g.handle)


def test_multi_use_grant_allows_repeat(service):
    g = _grant(service, single_use=False)
    a = service.redeem(ctx=_ctx(AGENT_A), handle=g.handle)
    b = service.redeem(ctx=_ctx(AGENT_A), handle=g.handle)
    assert a.credential and b.credential


# 4 -----------------------------------------------------------------------
def test_revoked_grant_fails(service):
    g = _grant(service)
    service.revoke(grant_id=g.grant_id, reason="compromised")
    with pytest.raises(BrokerDenied):
        service.redeem(ctx=_ctx(AGENT_A), handle=g.handle)


def test_revoke_is_idempotent_and_nondisclosing(service):
    # revoking an unknown grant returns the same success (no oracle)
    assert service.revoke(grant_id="does-not-exist") is True
    g = _grant(service)
    assert service.revoke(grant_id=g.grant_id) is True
    assert service.revoke(grant_id=g.grant_id) is True


# 5 -----------------------------------------------------------------------
def test_root_secret_never_returned_only_derived(service):
    g = _grant(service)
    res = service.redeem(ctx=_ctx(AGENT_A), handle=g.handle)
    assert res.credential != ROOT_SECRET.decode()
    assert ROOT_SECRET.decode() not in res.credential
    assert res.credential.startswith("fkderiv_")


def test_derived_credential_differs_per_redeemer(service):
    # Two different bound grants for two identities yield different derived creds.
    g1 = _grant(service, redeemer_identity=AGENT_A.principal)
    g2 = _grant(service, redeemer_identity=AGENT_B.principal, single_use=False)
    r1 = service.redeem(ctx=_ctx(AGENT_A), handle=g1.handle)
    r2 = service.redeem(ctx=_ctx(AGENT_B), handle=g2.handle)
    assert r1.credential != r2.credential


# 6 -----------------------------------------------------------------------
def test_caller_asserted_identity_is_ignored(service):
    # Grant bound to A. Caller authenticates as B but ASSERTS it is A.
    g = _grant(service, redeemer_identity=AGENT_A.principal)
    with pytest.raises(BrokerDenied):
        service.redeem(
            ctx=_ctx(AGENT_B, asserted=AGENT_A.principal), handle=g.handle
        )


def test_asserted_identity_cannot_upgrade_authenticated(service):
    # Grant bound to B; caller authenticated as B but asserts it is A. Authz uses
    # the authenticated B, so it still succeeds (assertion neither helps nor hurts).
    g = _grant(service, redeemer_identity=AGENT_B.principal, single_use=False)
    res = service.redeem(ctx=_ctx(AGENT_B, asserted="repo:evil/attacker"), handle=g.handle)
    assert res.credential


# 7 -----------------------------------------------------------------------
def test_macaroon_attenuation_narrows_and_cannot_widen(service, db):
    g = _grant(service, scope={"repos": ["FuzeAgent", "FuzeBI"], "action": "read"})
    row = db.query(Grant).filter(Grant.grant_id == g.grant_id).one()

    # A narrower handle (drop FuzeBI) still verifies for A.
    narrowed = macaroons.attenuate(g.handle, caveat='scope <= {"action":"read","repos":["FuzeAgent"]}')
    bounds = macaroons.verify_handle(
        handle=narrowed, root_key=row.root_key, grant_id=g.grant_id, caller=AGENT_A.principal
    )
    assert bounds.scope["repos"] == ["FuzeAgent"]

    # Trying to WIDEN (change redeemer to B) just adds a constraint that fails —
    # you cannot remove the original 'redeemer = A' caveat, so B can never verify.
    widened = macaroons.attenuate(g.handle, caveat=f"redeemer = {AGENT_B.principal}")
    with pytest.raises(ValueError):
        macaroons.verify_handle(
            handle=widened, root_key=row.root_key, grant_id=g.grant_id, caller=AGENT_B.principal
        )
    # And the original bound caller A can't satisfy the extra conflicting caveat.
    with pytest.raises(ValueError):
        macaroons.verify_handle(
            handle=widened, root_key=row.root_key, grant_id=g.grant_id, caller=AGENT_A.principal
        )


def test_redeem_attenuated_handle_uses_narrowed_scope(service):
    # B grants A a 2-repo scope; A (or an intermediary) attenuates to 1 repo before
    # redeeming. The released credential must carry the NARROWED scope.
    g = _grant(service, scope={"repos": ["FuzeAgent", "FuzeBI"], "action": "read"})
    narrowed = macaroons.attenuate(
        g.handle, caveat='scope <= {"action":"read","repos":["FuzeAgent"]}'
    )
    res = service.redeem(ctx=_ctx(AGENT_A), handle=narrowed)
    assert res.scope["repos"] == ["FuzeAgent"]


def test_tampered_handle_fails(service, db):
    g = _grant(service)
    row = db.query(Grant).filter(Grant.grant_id == g.grant_id).one()
    # forge a macaroon with a different (attacker) root key but same grant id
    forged = macaroons.mint_handle(
        root_key=b"attacker-key-32-bytes-xxxxxxxxxx!",
        grant_id=g.grant_id,
        redeemer=AGENT_A.principal,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
        scope={},
        single_use=True,
    )
    with pytest.raises(BrokerDenied):
        service.redeem(ctx=_ctx(AGENT_A), handle=forged)


# 8 -----------------------------------------------------------------------
def test_denials_are_nondisclosing(service):
    g = _grant(service)
    # unknown grant
    fake = macaroons.mint_handle(
        root_key=b"x" * 32, grant_id="deadbeef", redeemer=AGENT_A.principal,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=5), scope={}, single_use=True,
    )
    try:
        service.redeem(ctx=_ctx(AGENT_A), handle=fake)
        assert False, "should deny"
    except BrokerDenied as e1:
        msg_unknown = e1.public_message
    # existing grant, wrong caller
    try:
        service.redeem(ctx=_ctx(AGENT_B), handle=g.handle)
        assert False, "should deny"
    except BrokerDenied as e2:
        msg_unauth = e2.public_message
    assert msg_unknown == msg_unauth == BrokerDenied.PUBLIC_MESSAGE


# capability delegation (operation grant) ---------------------------------
def test_operation_grant_returns_scoped_token_not_secret(service):
    g = _grant(service, secret_ref=None, operation="send_email_via_sendgrid")
    res = service.redeem(ctx=_ctx(AGENT_A), handle=g.handle)
    assert res.kind == "operation_token"
    assert ROOT_SECRET.decode() not in res.credential


# 10 (RFC 8693) -----------------------------------------------------------
def test_mint_token_exchange_binds_authenticated_identity(service):
    from jose import jwt

    token = service.mint_token(ctx=_ctx(AGENT_A), audience="FuzeBI", scope="read:reports")
    claims = jwt.decode(
        token.access_token, "a-strong-broker-signing-key-1234567890", algorithms=["HS256"], audience="FuzeBI"
    )
    assert claims["sub"] == AGENT_A.principal
    assert claims["act"]["sub"] == AGENT_A.principal
    assert claims["scope"] == "read:reports"
    assert token.issued_token_type.endswith("access_token")


def test_mint_token_requires_authenticated_identity(service):
    with pytest.raises(BrokerDenied):
        service.mint_token(ctx=_ctx(None, asserted=AGENT_A.principal), audience="x", scope="y")


# high sensitivity -> approval gate ---------------------------------------
def test_high_sensitivity_requires_approval(service, db):
    g = _grant(service, sensitivity="high")
    with pytest.raises(ApprovalRequired):
        service.redeem(ctx=_ctx(AGENT_A), handle=g.handle)


def test_high_sensitivity_releases_after_approval(service, db):
    from app.models.approval import ApprovalRequest

    g = _grant(service, sensitivity="high")
    with pytest.raises(ApprovalRequired):
        service.redeem(ctx=_ctx(AGENT_A), handle=g.handle)
    row = db.query(Grant).filter(Grant.grant_id == g.grant_id).one()
    req = db.query(ApprovalRequest).filter(ApprovalRequest.id == row.approval_request_id).one()
    req.status = "approved"
    db.commit()
    res = service.redeem(ctx=_ctx(AGENT_A), handle=g.handle)
    assert res.credential


def test_oidc_transport_identity_projection():
    ident = transport_from_oidc({"repo": "izzywdev/FuzeAgent"})
    assert ident.principal == "repo:izzywdev/FuzeAgent"
    assert ident.method == "oidc"
