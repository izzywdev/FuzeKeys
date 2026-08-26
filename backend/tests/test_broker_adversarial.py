"""
INDEPENDENT, ADVERSARIAL verification of the FuzeKeys secret-broker.

Author: independent test-engineer (honest grader). These tests were written
WITHOUT trusting the builder's own suite (test_broker_service.py etc.). Each test
tries to *break* one of the broker's promised security invariants. A failing test
here against a real weakness is a valid, valuable deliverable — it BLOCKS the merge
of PR #59 until backend-engineer fixes the implementation.

Harness matches the repo's existing broker unit tests: import ONLY the broker +
model modules (app.main has a pre-existing cv2 import break) and run the
synchronous BrokerService core against in-memory SQLite.

Invariants under test (from the task brief):
  1. Redeem as the WRONG identity is denied; asserted identity is never trusted.
  2. Replay / double-spend / expired / revoked all denied.
  3. Root secret never leaves the vault; derived-only; differs per redeemer.
  4. Macaroon tampering / WIDENING must fail; attenuation narrows only.
  5. Non-disclosure: unknown / unauthorized / revoked / expired -> same shape.
  6. Envelope: sealed-to-recipient opens only with the recipient key.
  7. MCP path and REST header-mapping enforce the SAME transport-identity rule.
  8. mint_token (RFC 8693): audience/scope-bound, short-TTL, bound to authed id.
"""
import json
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.models  # noqa: F401  registers every table on Base.metadata
from app.broker import (
    BrokerConfig,
    BrokerDenied,
    BrokerService,
    InMemoryVault,
    TransportContext,
    TransportIdentity,
    envelope,
    macaroons,
    runtime,
)
from app.broker.errors import ApprovalRequired
from app.database import Base
from app.models.approval import AuditLog
from app.models.grant import Grant

ROOT_SECRET = b"super-long-lived-root-token-DO-NOT-LEAK-EVER"
SECRET_REF = "openbao:kv/identities/1/github/ci-token"

# Transport identities. Principals mirror OIDC `repo:` claims.
A = TransportIdentity(principal="repo:izzywdev/FuzeAgent", method="oidc")
B = TransportIdentity(principal="repo:izzywdev/FuzeBI", method="oidc")
EVIL = TransportIdentity(principal="repo:evil/attacker", method="oidc")

SIGNING_KEY = "a-strong-broker-signing-key-0123456789abcdef"


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
    cfg = BrokerConfig(
        signing_key=SIGNING_KEY, max_ttl_seconds=3600, default_ttl_seconds=300
    )
    return BrokerService(db, config=cfg, vault=vault)


def _ctx(authed, asserted=None):
    return TransportContext(authenticated=authed, asserted_identity=asserted)


def _grant(service, **overrides):
    kwargs = dict(
        grantor=B,
        redeemer_identity=A.principal,
        scope={"repos": ["FuzeAgent"], "action": "read"},
        ttl_seconds=300,
        secret_ref=SECRET_REF,
        single_use=True,
        sensitivity="medium",
    )
    kwargs.update(overrides)
    return service.grant(**kwargs)


# ======================================================================
# 1. WRONG-IDENTITY REDEEM
# ======================================================================
def test_grant_bound_to_A_cannot_be_redeemed_by_B(service):
    """A grant bound to A, redeemed by a *different* authenticated identity B, is denied."""
    g = _grant(service, redeemer_identity=A.principal)
    with pytest.raises(BrokerDenied):
        service.redeem(ctx=_ctx(B), handle=g.handle)


def test_asserted_identity_cannot_override_transport_identity(service):
    """Caller is authenticated as B but ASSERTS it is A (via ctx.asserted_identity).
    Only the transport identity counts -> must be denied for an A-bound grant."""
    g = _grant(service, redeemer_identity=A.principal)
    with pytest.raises(BrokerDenied):
        service.redeem(ctx=_ctx(B, asserted=A.principal), handle=g.handle)


def test_no_authenticated_identity_fails_closed(service):
    """An asserted-only request (no verified transport identity) can never redeem."""
    g = _grant(service, redeemer_identity=A.principal)
    with pytest.raises(BrokerDenied):
        service.redeem(ctx=_ctx(None, asserted=A.principal), handle=g.handle)


def test_asserting_evil_identity_does_not_help_authenticated_caller(service):
    """Authenticated A asserting it is 'evil/attacker' still authorizes on A (assertion ignored)."""
    g = _grant(service, redeemer_identity=A.principal)
    res = service.redeem(ctx=_ctx(A, asserted=EVIL.principal), handle=g.handle)
    assert res.credential  # authz used the authenticated A, not the asserted evil


# ======================================================================
# 2. REPLAY / DOUBLE-SPEND / EXPIRED / REVOKED
# ======================================================================
def test_single_use_grant_cannot_be_redeemed_twice(service):
    g = _grant(service, single_use=True)
    first = service.redeem(ctx=_ctx(A), handle=g.handle)
    assert first.credential
    with pytest.raises(BrokerDenied):
        service.redeem(ctx=_ctx(A), handle=g.handle)


def test_single_use_replay_via_attenuated_handle_still_denied(service):
    """Adversary re-serializes the handle (adds a harmless caveat) to try to dodge the
    single-use DB counter. The DB row is authoritative -> 2nd redeem must fail."""
    g = _grant(service, single_use=True)
    service.redeem(ctx=_ctx(A), handle=g.handle)
    replay = macaroons.attenuate(g.handle, caveat="single_use = true")
    with pytest.raises(BrokerDenied):
        service.redeem(ctx=_ctx(A), handle=replay)


def test_expired_grant_denied(service, db):
    g = _grant(service, ttl_seconds=5)
    row = db.query(Grant).filter(Grant.grant_id == g.grant_id).one()
    row.expires_at = datetime.now(timezone.utc) - timedelta(seconds=10)
    db.commit()
    with pytest.raises(BrokerDenied):
        service.redeem(ctx=_ctx(A), handle=g.handle)


def test_revoked_grant_denied(service):
    g = _grant(service)
    service.revoke(grant_id=g.grant_id, reason="compromised")
    with pytest.raises(BrokerDenied):
        service.redeem(ctx=_ctx(A), handle=g.handle)


def test_revoke_between_grant_and_redeem_blocks_release(service):
    """A multi-use grant redeemed once, then revoked, must not release again."""
    g = _grant(service, single_use=False)
    assert service.redeem(ctx=_ctx(A), handle=g.handle).credential
    service.revoke(grant_id=g.grant_id)
    with pytest.raises(BrokerDenied):
        service.redeem(ctx=_ctx(A), handle=g.handle)


# ======================================================================
# 3. ROOT-SECRET EXTRACTION
# ======================================================================
def test_redeem_never_returns_root_secret(service):
    g = _grant(service)
    res = service.redeem(ctx=_ctx(A), handle=g.handle)
    assert res.credential != ROOT_SECRET.decode()
    assert ROOT_SECRET.decode() not in res.credential
    assert "DO-NOT-LEAK" not in res.credential
    assert res.credential.startswith("fkderiv_")


def test_two_distinct_redeemers_get_different_derived_creds(service):
    """Same underlying secret_ref, two different bound redeemers -> different derived material."""
    g_a = _grant(service, redeemer_identity=A.principal)
    g_b = _grant(service, redeemer_identity=B.principal)
    ra = service.redeem(ctx=_ctx(A), handle=g_a.handle)
    rb = service.redeem(ctx=_ctx(B), handle=g_b.handle)
    assert ra.credential != rb.credential
    assert ROOT_SECRET.decode() not in ra.credential
    assert ROOT_SECRET.decode() not in rb.credential


def test_root_secret_never_written_to_audit_log(service, db):
    g = _grant(service)
    service.redeem(ctx=_ctx(A), handle=g.handle)
    rows = db.query(AuditLog).all()
    assert rows, "expected audit entries"
    for r in rows:
        blob = f"{r.resource_ref}|{r.decision}"
        assert ROOT_SECRET.decode() not in blob
        assert "DO-NOT-LEAK" not in blob


def test_handle_carries_no_secret_material(service):
    g = _grant(service)
    assert ROOT_SECRET.decode() not in g.handle
    assert "DO-NOT-LEAK" not in g.handle


# ======================================================================
# 4. MACAROON TAMPERING / WIDENING
# ======================================================================
def test_forged_root_key_rejected(service, db):
    """A macaroon minted under an attacker's root key (same grant_id) must fail verification."""
    g = _grant(service)
    forged = macaroons.mint_handle(
        root_key=b"attacker-key-32-bytes-xxxxxxxxxx!",
        grant_id=g.grant_id,
        redeemer=A.principal,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
        scope={"repos": ["FuzeAgent"], "action": "read"},
        single_use=True,
    )
    with pytest.raises(BrokerDenied):
        service.redeem(ctx=_ctx(A), handle=forged)


def test_cannot_rebind_redeemer_by_appending_caveat(service, db):
    """Appending `redeemer = B` cannot REMOVE the original `redeemer = A` caveat; B never verifies."""
    g = _grant(service, redeemer_identity=A.principal)
    row = db.query(Grant).filter(Grant.grant_id == g.grant_id).one()
    rebound = macaroons.attenuate(g.handle, caveat=f"redeemer = {B.principal}")
    with pytest.raises(ValueError):
        macaroons.verify_handle(
            handle=rebound,
            root_key=row.root_key,
            grant_id=g.grant_id,
            caller=B.principal,
        )
    with pytest.raises(BrokerDenied):
        service.redeem(ctx=_ctx(B), handle=rebound)


def test_cannot_extend_ttl_by_appending_caveat(service, db):
    """Appending a LATER `expires <=` caveat cannot override the earlier, tighter one."""
    g = _grant(service, ttl_seconds=300)
    row = db.query(Grant).filter(Grant.grant_id == g.grant_id).one()
    # Force the ORIGINAL caveat to be in the past by rewriting the row's expiry AND
    # appending a far-future caveat. The tighter (earlier) expiry must win.
    far_future = (datetime.now(timezone.utc) + timedelta(days=3650)).isoformat()
    extended = macaroons.attenuate(g.handle, caveat=f"expires <= {far_future}")
    # The grant itself is not yet expired, so this must still verify with the
    # *original* (tighter) expiry as the ceiling, never the far-future one.
    bounds = macaroons.verify_handle(
        handle=extended, root_key=row.root_key, grant_id=g.grant_id, caller=A.principal
    )
    original_expiry = row.expires_at
    if original_expiry.tzinfo is None:
        original_expiry = original_expiry.replace(tzinfo=timezone.utc)
    assert bounds.expires_at <= original_expiry + timedelta(
        seconds=2
    ), "appended expiry caveat widened the TTL ceiling"


def test_attenuation_narrows_a_list_scope(service):
    """Legitimate attenuation: narrowing a repos list is honored and redeems with the narrowed scope."""
    g = _grant(service, scope={"repos": ["FuzeAgent", "FuzeBI"], "action": "read"})
    narrowed = macaroons.attenuate(
        g.handle, caveat='scope <= {"action":"read","repos":["FuzeAgent"]}'
    )
    res = service.redeem(ctx=_ctx(A), handle=narrowed)
    assert res.scope["repos"] == ["FuzeAgent"]


def test_attenuation_cannot_inject_new_scope_key_derived(service):
    """ADVERSARIAL (invariant #4): the doctrine says caveats can ONLY narrow. The holder
    appends a `scope <=` caveat introducing NEW capability keys the grantor never
    authorized (`admin`, `delete`). The released credential's effective scope MUST NOT
    contain those injected keys — otherwise a holder can self-escalate its authority."""
    g = _grant(
        service, scope={"repos": ["FuzeAgent"], "action": "read"}, single_use=False
    )
    evil = macaroons.attenuate(
        g.handle,
        caveat='scope <= {"admin":true,"delete":["prod"],"repos":["FuzeAgent"]}',
    )
    res = service.redeem(ctx=_ctx(A), handle=evil)
    assert "admin" not in res.scope, f"scope widened: injected 'admin' -> {res.scope}"
    assert "delete" not in res.scope, f"scope widened: injected 'delete' -> {res.scope}"


def test_attenuation_cannot_inject_new_scope_key_operation_token(service):
    """Same escalation via the operation-token (capability delegation) path: the JWT scope
    claim MUST NOT carry holder-injected keys beyond what the grantor authorized."""
    g = _grant(
        service,
        secret_ref=None,
        operation="send_email_via_sendgrid",
        scope={"action": "send"},
        single_use=False,
    )
    evil = macaroons.attenuate(
        g.handle, caveat='scope <= {"action":"send","admin":true}'
    )
    res = service.redeem(ctx=_ctx(A), handle=evil)
    scope_claim = json.loads(res.scope) if isinstance(res.scope, str) else res.scope
    assert "admin" not in scope_claim, f"operation-token scope widened -> {scope_claim}"


def test_effective_scope_never_exceeds_original_grant_scope(service):
    """Defense-in-depth: whatever caveats are appended, the released scope must be a
    SUBSET of the scope the grantor originally authorized (row.scope)."""
    original = {"repos": ["FuzeAgent"], "action": "read"}
    g = _grant(service, scope=dict(original), single_use=False)
    evil = macaroons.attenuate(
        g.handle, caveat='scope <= {"repos":["FuzeAgent"],"action":"read","extra":"x"}'
    )
    res = service.redeem(ctx=_ctx(A), handle=evil)
    released = json.loads(res.scope) if isinstance(res.scope, str) else res.scope
    extra_keys = set(released) - set(original)
    assert (
        not extra_keys
    ), f"released scope introduced keys not in the grant: {extra_keys}"


# ======================================================================
# 5. NON-DISCLOSURE (no oracle)
# ======================================================================
def test_unknown_unauthorized_revoked_expired_share_one_message(service, db):
    messages = set()

    # unknown grant (valid macaroon over a grant_id that does not exist)
    fake = macaroons.mint_handle(
        root_key=b"x" * 32,
        grant_id="deadbeefdeadbeef",
        redeemer=A.principal,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
        scope={},
        single_use=True,
    )
    with pytest.raises(BrokerDenied) as e:
        service.redeem(ctx=_ctx(A), handle=fake)
    messages.add(e.value.public_message)

    # unauthorized (exists, wrong caller)
    g1 = _grant(service)
    with pytest.raises(BrokerDenied) as e:
        service.redeem(ctx=_ctx(B), handle=g1.handle)
    messages.add(e.value.public_message)

    # revoked
    g2 = _grant(service)
    service.revoke(grant_id=g2.grant_id)
    with pytest.raises(BrokerDenied) as e:
        service.redeem(ctx=_ctx(A), handle=g2.handle)
    messages.add(e.value.public_message)

    # expired
    g3 = _grant(service, ttl_seconds=5)
    row = db.query(Grant).filter(Grant.grant_id == g3.grant_id).one()
    row.expires_at = datetime.now(timezone.utc) - timedelta(seconds=10)
    db.commit()
    with pytest.raises(BrokerDenied) as e:
        service.redeem(ctx=_ctx(A), handle=g3.handle)
    messages.add(e.value.public_message)

    assert messages == {
        BrokerDenied.PUBLIC_MESSAGE
    }, f"denial messages leak an oracle: {messages}"


def test_unresolvable_secret_ref_is_nondisclosing(db):
    """A grant whose secret_ref is missing from the vault denies with the SAME generic
    message (does not reveal whether the ref exists)."""
    empty_vault = InMemoryVault()  # no secrets at all
    svc = BrokerService(
        db,
        config=BrokerConfig(signing_key=SIGNING_KEY, max_ttl_seconds=3600),
        vault=empty_vault,
    )
    g = svc.grant(
        grantor=B,
        redeemer_identity=A.principal,
        scope={},
        ttl_seconds=300,
        secret_ref="missing:ref",
    )
    with pytest.raises(BrokerDenied) as e:
        svc.redeem(ctx=_ctx(A), handle=g.handle)
    assert e.value.public_message == BrokerDenied.PUBLIC_MESSAGE


# ======================================================================
# 6. ENVELOPE ENCRYPTION
# ======================================================================
def test_sealed_opens_only_with_recipient_key():
    recipient_priv, recipient_jwk = envelope.generate_recipient_keypair(2048)
    relay_priv, _ = envelope.generate_recipient_keypair(2048)
    pub = envelope.load_rsa_public_from_jwk(recipient_jwk)
    sealed = envelope.seal_to_recipient(b"top-secret-payload", pub)
    # recipient opens it
    assert envelope.open_sealed(sealed, recipient_priv) == b"top-secret-payload"
    # a relay / other key cannot
    with pytest.raises(Exception):
        envelope.open_sealed(sealed, relay_priv)


def test_sealed_bundle_contains_no_plaintext():
    recipient_priv, recipient_jwk = envelope.generate_recipient_keypair(2048)
    pub = envelope.load_rsa_public_from_jwk(recipient_jwk)
    sealed = envelope.seal_to_recipient(b"marker-plaintext-1234", pub)
    blob = sealed.to_json()
    assert "marker-plaintext-1234" not in blob


def test_tampered_ciphertext_fails_aead():
    recipient_priv, recipient_jwk = envelope.generate_recipient_keypair(2048)
    pub = envelope.load_rsa_public_from_jwk(recipient_jwk)
    sealed = envelope.seal_to_recipient(b"integrity-protected", pub)
    # flip a byte of the ciphertext -> GCM tag must reject
    bad = envelope.SealedSecret(
        wrapped_dek=sealed.wrapped_dek,
        nonce=sealed.nonce,
        ciphertext=("A" if sealed.ciphertext[0] != "A" else "B")
        + sealed.ciphertext[1:],
    )
    with pytest.raises(Exception):
        envelope.open_sealed(bad, recipient_priv)


# ======================================================================
# 7. SURFACE CONSISTENCY (REST header-mapping vs MCP)
# ======================================================================
def test_rest_header_mapping_ignores_asserted_identity_for_authz(service):
    """The REST surface builds its TransportContext via runtime.transport_from_headers.
    An `X-Asserted-Identity` header must never authorize — only the gateway-verified
    `X-Verified-Repo`/`X-Verified-Spiffe` header does. A grant bound to A cannot be
    redeemed by a request that is verified as B but asserts it is A."""
    g = _grant(service, redeemer_identity=A.principal)

    # (a) header asserts A but no verified transport identity -> fail closed
    ctx_asserted_only = runtime.transport_from_headers(
        {"x-asserted-identity": A.principal}
    )
    assert ctx_asserted_only.authenticated is None
    with pytest.raises(BrokerDenied):
        service.redeem(ctx=ctx_asserted_only, handle=g.handle)

    # (b) verified as B, asserts A -> authz uses B -> denied for A-bound grant
    ctx_b_asserts_a = runtime.transport_from_headers(
        {"x-verified-repo": "izzywdev/FuzeBI", "x-asserted-identity": A.principal}
    )
    assert ctx_b_asserts_a.authenticated.principal == B.principal
    with pytest.raises(BrokerDenied):
        service.redeem(ctx=ctx_b_asserts_a, handle=g.handle)


def test_rest_and_mcp_paths_agree_on_success(service):
    """The verified-A header path and the direct MCP ctx path release the same kind of cred."""
    from app.broker import mcp_tools

    g = _grant(service, redeemer_identity=A.principal, single_use=False)
    ctx_header = runtime.transport_from_headers(
        {"x-verified-repo": "izzywdev/FuzeAgent"}
    )
    assert ctx_header.authenticated.principal == A.principal
    out = mcp_tools.keys_redeem(service, ctx=ctx_header, grant_handle=g.handle)
    assert out["status"] == "released"
    assert out["kind"] == "derived_secret"


# ======================================================================
# 8. mint_token (RFC 8693)
# ======================================================================
def test_mint_token_is_bound_to_authenticated_identity(service):
    from jose import jwt

    tok = service.mint_token(ctx=_ctx(A), audience="FuzeBI", scope="read:reports")
    claims = jwt.decode(
        tok.access_token, SIGNING_KEY, algorithms=["HS256"], audience="FuzeBI"
    )
    assert claims["sub"] == A.principal
    assert claims["act"]["sub"] == A.principal
    assert claims["aud"] == "FuzeBI"
    assert claims["scope"] == "read:reports"


def test_mint_token_cannot_impersonate_via_assertion(service):
    """Authenticated A asserting it is EVIL still mints a token bound to A, never EVIL."""
    from jose import jwt

    tok = service.mint_token(
        ctx=_ctx(A, asserted=EVIL.principal), audience="X", scope="s"
    )
    claims = jwt.decode(
        tok.access_token, SIGNING_KEY, algorithms=["HS256"], audience="X"
    )
    assert claims["sub"] == A.principal


def test_mint_token_ttl_is_clamped_to_server_max(service):
    tok = service.mint_token(
        ctx=_ctx(A), audience="X", scope="s", ttl_seconds=10_000_000
    )
    assert tok.expires_in <= 3600, f"mint_token TTL not clamped: {tok.expires_in}"


def test_mint_token_requires_authenticated_identity(service):
    with pytest.raises(BrokerDenied):
        service.mint_token(
            ctx=_ctx(None, asserted=A.principal), audience="X", scope="s"
        )


# ======================================================================
# High-sensitivity approval gate (bonus lifecycle coverage)
# ======================================================================
def test_high_sensitivity_defers_to_human_approval(service):
    g = _grant(service, sensitivity="high")
    with pytest.raises(ApprovalRequired):
        service.redeem(ctx=_ctx(A), handle=g.handle)
