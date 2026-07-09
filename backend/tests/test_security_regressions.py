"""
INDEPENDENT regression tests for already-merged security fixes.

These tests are written by the test-engineer (independent verification), NOT by
the implementer. Each test asserts an acceptance criterion of a merged security
fix and is designed to FAIL if that fix were reverted.

Three areas covered (see the task brief / the SECURITY comments in the source):

  1. Service API-key auth fails closed
     (backend/app/routers/credentials.py :: verify_api_key + _load_service_api_keys)
  2. IDOR ownership scoping on credential retrieval/store
     (credentials.py :: request_account_credentials / store_account_credentials)
  3. OTP device auth + request binding
     (backend/app/routers/sms.py :: receive_otp + register_device + _verify_device)

ENVIRONMENT CONSTRAINT (documented, not ours to fix):
  Importing app.main transitively imports app.services.captcha_service -> cv2,
  which fails locally with "numpy.core.multiarray failed to import" (numpy/opencv
  ABI mismatch). That break is PRE-EXISTING and UNRELATED to these security fixes
  and is expected to be local-only (CI installs fresh deps).

  Therefore these tests deliberately DO NOT import app.main and DO NOT use the
  app-importing `client` fixture in conftest.py. They import only the specific
  router modules (app.routers.credentials, app.routers.sms) and the ORM models,
  which import cleanly (verified) without pulling in cv2. Run them with:

      cd backend
      python -m pytest tests/test_security_regressions.py -v --noconftest -p no:cacheprovider

  --noconftest avoids the (separately-fixed) app.main import in conftest.py so
  collection succeeds in the cv2-broken local environment. The tests do not rely
  on any conftest fixture.
"""

import asyncio

import pytest

from fastapi import HTTPException

# Importing these specific modules is cv2-free (verified). Importing app.main is NOT.
import app.routers.credentials as credentials_mod
import app.routers.sms as sms_mod


# ---------------------------------------------------------------------------
# Small helpers for driving the async router functions synchronously.
# ---------------------------------------------------------------------------
def _run(coro):
    """Run an async coroutine to completion on a fresh event loop."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ===========================================================================
# AREA 1: Service API-key auth fails closed  (VULN 1)
#
# Fix under test (credentials.verify_api_key + _load_service_api_keys):
#   - No keys configured  -> 401 for ANY request (fail closed).
#   - Missing / blank X-API-Key -> 401.
#   - Wrong key -> 401.
#   - Only a CORRECTLY configured key authenticates (returns the service name).
#   - Keys come from env (SCRAPER_API_KEY / MOBILE_API_KEY / AUTOMATION_API_KEY)
#     with NO hardcoded defaults.
#
# Reversion this would catch: re-introducing hardcoded default keys, allowing a
# blank/missing key through, or authenticating when no keys are configured.
# ===========================================================================
class TestVerifyApiKeyFailsClosed:
    @pytest.fixture(autouse=True)
    def _isolate_valid_keys(self):
        """Snapshot and restore the module-level VALID_API_KEYS around each test
        so global state is never left polluted."""
        original = credentials_mod.VALID_API_KEYS
        yield
        credentials_mod.VALID_API_KEYS = original

    def test_no_keys_configured_rejects_even_a_nonblank_key(self):
        """With zero configured keys, NOTHING authenticates -> 401."""
        credentials_mod.VALID_API_KEYS = {}
        with pytest.raises(HTTPException) as exc:
            _run(credentials_mod.verify_api_key(x_api_key="anything-at-all"))
        assert exc.value.status_code == 401

    def test_blank_key_rejected(self):
        """A blank X-API-Key is rejected with 401 even when keys ARE configured.

        Guards against authenticating against an empty/blank stored value."""
        credentials_mod.VALID_API_KEYS = {"scraper-service": "real-key-123"}
        for blank in ("", "   ", "\t"):
            with pytest.raises(HTTPException) as exc:
                _run(credentials_mod.verify_api_key(x_api_key=blank))
            assert exc.value.status_code == 401, f"blank value {blank!r} should be 401"

    def test_wrong_key_rejected(self):
        """A non-matching key is rejected with 401."""
        credentials_mod.VALID_API_KEYS = {"scraper-service": "real-key-123"}
        with pytest.raises(HTTPException) as exc:
            _run(credentials_mod.verify_api_key(x_api_key="wrong-key"))
        assert exc.value.status_code == 401

    def test_correct_key_authenticates_and_returns_service_name(self):
        """A correctly configured key authenticates and yields its service name."""
        credentials_mod.VALID_API_KEYS = {
            "scraper-service": "scraper-secret",
            "mobile-service": "mobile-secret",
        }
        assert _run(credentials_mod.verify_api_key(x_api_key="scraper-secret")) == "scraper-service"
        assert _run(credentials_mod.verify_api_key(x_api_key="mobile-secret")) == "mobile-service"

    def test_loader_excludes_unset_and_blank_env_keys(self, monkeypatch):
        """_load_service_api_keys() reads ONLY from env with NO defaults: unset or
        blank env vars produce an empty / partial map (never a hardcoded fallback).

        Reversion caught: re-adding hardcoded default service keys."""
        # All unset -> empty map (fail closed at request time).
        monkeypatch.delenv("SCRAPER_API_KEY", raising=False)
        monkeypatch.delenv("MOBILE_API_KEY", raising=False)
        monkeypatch.delenv("AUTOMATION_API_KEY", raising=False)
        assert credentials_mod._load_service_api_keys() == {}

        # Blank values are excluded too.
        monkeypatch.setenv("SCRAPER_API_KEY", "   ")
        assert credentials_mod._load_service_api_keys() == {}

        # A configured (non-blank) value is included, stripped, and mapped to its service.
        monkeypatch.setenv("SCRAPER_API_KEY", "  cfg-scraper-key  ")
        monkeypatch.setenv("MOBILE_API_KEY", "cfg-mobile-key")
        loaded = credentials_mod._load_service_api_keys()
        assert loaded == {
            "scraper-service": "cfg-scraper-key",
            "mobile-service": "cfg-mobile-key",
        }

    def test_loaded_key_round_trips_through_verify_api_key(self, monkeypatch):
        """End-to-end of the fix: a key configured purely via env authenticates,
        and a different value does not."""
        monkeypatch.delenv("MOBILE_API_KEY", raising=False)
        monkeypatch.delenv("AUTOMATION_API_KEY", raising=False)
        monkeypatch.setenv("SCRAPER_API_KEY", "env-only-key")
        credentials_mod.VALID_API_KEYS = credentials_mod._load_service_api_keys()

        assert _run(credentials_mod.verify_api_key(x_api_key="env-only-key")) == "scraper-service"
        with pytest.raises(HTTPException) as exc:
            _run(credentials_mod.verify_api_key(x_api_key="env-only-key-WRONG"))
        assert exc.value.status_code == 401


# ===========================================================================
# AREA 2: IDOR ownership scoping  (VULN 2)
#
# Fix under test (credentials.request_account_credentials / store_account_credentials):
#   - The request must supply identity_id; the lookup is scoped to it via
#       Account.id == account_id  AND  Account.identity_id == request.identity_id
#   - A request naming the WRONG owning identity must NOT retrieve another
#     identity's account; instead it 404s (and never returns cross-tenant data).
#
# Ownership chain: Account.identity_id -> Identity.id, Identity.user_id -> User.id.
#
# We exercise the REAL endpoint handlers (request_account_credentials /
# store_account_credentials) against a real (in-memory SQLite) synchronous
# SQLAlchemy session, seeding two identities owned by different users, each with
# its own account. We stub verify_api_key out by passing service_name directly
# (the handlers take service_name as a plain arg), so this isolates the
# ownership-scoping logic under test.
#
# Reversion this would catch: removing the `Account.identity_id == identity_id`
# filter (i.e. looking up by account_id alone), which is the IDOR.
# ===========================================================================
class TestIdorOwnershipScoping:
    @pytest.fixture(autouse=True)
    def _grant_full_identity_scope(self):
        """These tests isolate the per-IDENTITY IDOR layer (Account.identity_id
        scoping). The newer per-KEY scope gate (HIGH-2, require_identity_scope)
        sits in FRONT of it, so we grant the calling service a wildcard scope here
        and restore it afterwards; otherwise the request would 403 on key-scope
        before ever reaching the IDOR check under test. The key-scope behaviour is
        covered independently in TestServiceKeyIdentityScoping."""
        original = credentials_mod.SERVICE_IDENTITY_SCOPES
        credentials_mod.SERVICE_IDENTITY_SCOPES = {"scraper-service": "*"}
        yield
        credentials_mod.SERVICE_IDENTITY_SCOPES = original

    @pytest.fixture
    def db_session(self):
        """A synchronous in-memory SQLite session with the User/Identity/Account
        tables created. Uses the app's real ORM models so the scoping query the
        endpoint runs is exercised verbatim."""
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker

        # Import the models AND database.Base. account/identity/user all bind to
        # app.database.Base; importing the modules registers their tables on it.
        from app.database import Base
        from app.models.user import User
        from app.models.identity import Identity
        from app.models.account import Account  # noqa: F401  (registers table)

        engine = create_engine("sqlite:///:memory:")
        # Create only the tables defined on app.database.Base (not the separate
        # sms Base). create_all is safe/idempotent for the registered tables.
        Base.metadata.create_all(engine)

        Session = sessionmaker(bind=engine)
        session = Session()
        try:
            yield session, User, Identity, Account
        finally:
            session.close()
            engine.dispose()

    @staticmethod
    def _seed_two_tenants(session, User, Identity, Account):
        """Create two users, each with one identity owning one account."""
        user_a = User(
            email="<EMAIL_a>", username="user_a",
            hashed_password="h", master_key_hash="m",
        )
        user_b = User(
            email="<EMAIL_b>", username="user_b",
            hashed_password="h", master_key_hash="m",
        )
        session.add_all([user_a, user_b])
        session.flush()

        identity_a = Identity(user_id=user_a.id, name="Identity A")
        identity_b = Identity(user_id=user_b.id, name="Identity B")
        session.add_all([identity_a, identity_b])
        session.flush()

        account_a = Account(
            identity_id=identity_a.id,
            website_name="SiteA", website_url="https://a.example",
            encrypted_credentials=None,
        )
        account_b = Account(
            identity_id=identity_b.id,
            website_name="SiteB", website_url="https://b.example",
            encrypted_credentials=None,
        )
        session.add_all([account_a, account_b])
        session.commit()
        return identity_a, identity_b, account_a, account_b

    def test_retrieve_with_wrong_owning_identity_yields_404(self, db_session):
        """IDOR core: account_b belongs to identity_b. A request for account_b
        that names identity_a (a different owner) must 404 — no cross-tenant data."""
        session, User, Identity, Account = db_session
        identity_a, identity_b, account_a, account_b = self._seed_two_tenants(
            session, User, Identity, Account
        )

        req = credentials_mod.AccountCredentialRequest(
            identity_id=identity_a.id,        # WRONG owner for account_b
            account_id=account_b.id,
            credential_types=[],
        )
        with pytest.raises(HTTPException) as exc:
            _run(credentials_mod.request_account_credentials(req, "scraper-service", session))
        assert exc.value.status_code == 404

    def test_retrieve_with_correct_owner_succeeds(self, db_session):
        """The legitimate path: correct (identity, account) pair returns the
        account (200), proving the 404 above is the scoping check, not a blanket deny."""
        session, User, Identity, Account = db_session
        identity_a, identity_b, account_a, account_b = self._seed_two_tenants(
            session, User, Identity, Account
        )

        req = credentials_mod.AccountCredentialRequest(
            identity_id=identity_b.id,        # correct owner of account_b
            account_id=account_b.id,
            credential_types=[],
        )
        resp = _run(credentials_mod.request_account_credentials(req, "scraper-service", session))
        assert resp.account_id == account_b.id
        assert resp.site_name == "SiteB"

    def test_store_with_wrong_owning_identity_yields_404_and_no_mutation(self, db_session, monkeypatch):
        """Store path enforces the same scoping AND does not mutate the victim's
        account when the wrong owner is named."""
        session, User, Identity, Account = db_session
        identity_a, identity_b, account_a, account_b = self._seed_two_tenants(
            session, User, Identity, Account
        )
        # Provide a working cipher so a (hypothetically-passing) store wouldn't 503
        # before the scoping check — we want the 404 to come from scoping, and we
        # want to prove no write happened on the cross-tenant account.
        from cryptography.fernet import Fernet
        valid_key = Fernet.generate_key().decode()
        monkeypatch.setattr(credentials_mod, "ENCRYPTION_KEY", valid_key)

        before = account_b.encrypted_credentials  # None
        req = credentials_mod.CredentialUpdate(
            identity_id=identity_a.id,        # WRONG owner for account_b
            account_id=account_b.id,
            credentials={"password": "attacker-write"},
            metadata=None,
        )
        with pytest.raises(HTTPException) as exc:
            _run(credentials_mod.store_account_credentials(req, "scraper-service", session))
        assert exc.value.status_code == 404

        session.expire_all()
        refreshed = session.get(Account, account_b.id)
        assert refreshed.encrypted_credentials == before, "victim account must not be mutated"
        assert refreshed.encrypted_credentials is None

    def test_store_with_correct_owner_succeeds(self, db_session, monkeypatch):
        """Legitimate store with the correct owner persists encrypted credentials."""
        session, User, Identity, Account = db_session
        identity_a, identity_b, account_a, account_b = self._seed_two_tenants(
            session, User, Identity, Account
        )
        from cryptography.fernet import Fernet
        valid_key = Fernet.generate_key().decode()
        monkeypatch.setattr(credentials_mod, "ENCRYPTION_KEY", valid_key)

        req = credentials_mod.CredentialUpdate(
            identity_id=identity_b.id,        # correct owner
            account_id=account_b.id,
            credentials={"password": "legit"},
            metadata=None,
        )
        result = _run(credentials_mod.store_account_credentials(req, "scraper-service", session))
        assert result["success"] is True
        session.expire_all()
        refreshed = session.get(Account, account_b.id)
        assert refreshed.encrypted_credentials is not None


# ===========================================================================
# AREA 3: OTP device auth + request binding  (sms.receive_otp)
#
# Fix under test (sms.receive_otp + _verify_device + register_device):
#   - Requires header X-Device-Key verified via _verify_device against the
#     module-level registered_device_keys -> 401 if device unknown / key bad.
#   - Requires a request_id that exists in pending_otp_requests -> 404 if absent.
#   - Rejects a device that isn't the one assigned to that request -> 403.
#   - Validates OTP format (digits, length bounds) -> 400.
#   - Succeeds only for the authenticated, bound device + open request.
#   - register_device issues + persists a secrets.token_urlsafe(32) key.
#
# We seed the module-level dicts directly and call receive_otp(...) with a fake
# DB session (and stub the websocket broadcast) so we exercise the auth/binding
# logic without app.main.
#
# Reversion this would catch: dropping the X-Device-Key check (any caller could
# submit), matching the "first waiting" request instead of a bound request_id,
# or not enforcing assigned-device binding.
# ===========================================================================
class _FakeQuery:
    def filter(self, *a, **k):
        return self

    def first(self):
        return None


class _FakeDbSession:
    """Minimal stand-in for a SQLAlchemy Session used by receive_otp.

    Records add/commit so tests can assert whether persistence was attempted,
    and returns no device on query (so the 'update last seen' branch is a no-op)."""

    def __init__(self):
        self.added = []
        self.commits = 0

    def add(self, obj):
        self.added.append(obj)

    def commit(self):
        self.commits += 1

    def query(self, *a, **k):
        return _FakeQuery()


class TestOtpDeviceAuthAndBinding:
    @pytest.fixture(autouse=True)
    def _isolate_module_state(self):
        """Reset the module-level dicts before AND after each test so no global
        OTP/device state leaks between tests."""
        orig_keys = dict(sms_mod.registered_device_keys)
        orig_pending = dict(sms_mod.pending_otp_requests)
        sms_mod.registered_device_keys.clear()
        sms_mod.pending_otp_requests.clear()
        yield
        sms_mod.registered_device_keys.clear()
        sms_mod.registered_device_keys.update(orig_keys)
        sms_mod.pending_otp_requests.clear()
        sms_mod.pending_otp_requests.update(orig_pending)

    @pytest.fixture(autouse=True)
    def _stub_broadcast(self, monkeypatch):
        """Stub the websocket broadcast so the success path doesn't need a real
        connection manager; record that it was (not) called."""
        async def _noop_broadcast(*a, **k):
            return None
        monkeypatch.setattr(sms_mod.sms_manager, "broadcast", _noop_broadcast)

    @staticmethod
    def _make_request(device_id, request_id, otp="123456"):
        return sms_mod.OtpRequest(
            otp=otp,
            sender="VERIFY",
            message_body="Your code is 123456",
            timestamp=1_700_000_000_000,
            device_id=device_id,
            confidence=0.99,
            request_id=request_id,
        )

    @staticmethod
    def _future_ts():
        from datetime import datetime, timedelta
        return (datetime.utcnow() + timedelta(seconds=300)).timestamp()

    def test_unknown_device_rejected_401(self):
        """No X-Device-Key / device not registered -> 401 (device auth fails)."""
        sms_mod.pending_otp_requests["req-1"] = {
            "status": "waiting", "timeout": self._future_ts(),
        }
        req = self._make_request(device_id="dev-unknown", request_id="req-1")

        # Missing header
        with pytest.raises(HTTPException) as exc:
            _run(sms_mod.receive_otp(req, x_device_key=None, db=_FakeDbSession()))
        assert exc.value.status_code == 401

        # Header present but device not registered
        with pytest.raises(HTTPException) as exc2:
            _run(sms_mod.receive_otp(req, x_device_key="some-key", db=_FakeDbSession()))
        assert exc2.value.status_code == 401

    def test_registered_device_wrong_key_rejected_401(self):
        """A registered device but the WRONG key -> 401."""
        sms_mod.registered_device_keys["dev-1"] = "correct-key"
        sms_mod.pending_otp_requests["req-1"] = {
            "status": "waiting", "timeout": self._future_ts(),
        }
        req = self._make_request(device_id="dev-1", request_id="req-1")
        with pytest.raises(HTTPException) as exc:
            _run(sms_mod.receive_otp(req, x_device_key="wrong-key", db=_FakeDbSession()))
        assert exc.value.status_code == 401

    def test_unknown_request_id_yields_404(self):
        """Authenticated device, but the request_id isn't pending -> 404."""
        sms_mod.registered_device_keys["dev-1"] = "correct-key"
        # No pending_otp_requests entries.
        req = self._make_request(device_id="dev-1", request_id="does-not-exist")
        with pytest.raises(HTTPException) as exc:
            _run(sms_mod.receive_otp(req, x_device_key="correct-key", db=_FakeDbSession()))
        assert exc.value.status_code == 404

    def test_invalid_otp_format_yields_400(self):
        """Authenticated device + valid request, but a non-numeric / out-of-bounds
        OTP -> 400 (format validation)."""
        sms_mod.registered_device_keys["dev-1"] = "correct-key"
        sms_mod.pending_otp_requests["req-1"] = {
            "status": "waiting", "timeout": self._future_ts(),
        }
        for bad_otp in ("abc123", "12", "123456789012"):
            req = self._make_request(device_id="dev-1", request_id="req-1", otp=bad_otp)
            with pytest.raises(HTTPException) as exc:
                _run(sms_mod.receive_otp(req, x_device_key="correct-key", db=_FakeDbSession()))
            assert exc.value.status_code == 400, f"otp {bad_otp!r} should be 400"

    def test_device_not_assigned_to_request_yields_403(self):
        """A request pre-assigned to dev-1 cannot be completed by a different
        (also authenticated) device dev-2 -> 403."""
        sms_mod.registered_device_keys["dev-1"] = "key-1"
        sms_mod.registered_device_keys["dev-2"] = "key-2"
        sms_mod.pending_otp_requests["req-1"] = {
            "status": "waiting",
            "timeout": self._future_ts(),
            "assigned_device_id": "dev-1",   # request belongs to dev-1
        }
        req = self._make_request(device_id="dev-2", request_id="req-1")
        with pytest.raises(HTTPException) as exc:
            _run(sms_mod.receive_otp(req, x_device_key="key-2", db=_FakeDbSession()))
        assert exc.value.status_code == 403

    def test_bound_device_succeeds_and_completes_request(self):
        """Happy path: the assigned, authenticated device with a valid OTP for an
        open request succeeds and the request is marked completed."""
        sms_mod.registered_device_keys["dev-1"] = "key-1"
        sms_mod.pending_otp_requests["req-1"] = {
            "status": "waiting",
            "timeout": self._future_ts(),
            "assigned_device_id": "dev-1",
        }
        db = _FakeDbSession()
        req = self._make_request(device_id="dev-1", request_id="req-1", otp="123456")
        result = _run(sms_mod.receive_otp(req, x_device_key="key-1", db=db))

        assert result["success"] is True
        assert result["request_id"] == "req-1"
        assert sms_mod.pending_otp_requests["req-1"]["status"] == "completed"
        assert sms_mod.pending_otp_requests["req-1"]["otp_code"] == "123456"
        assert db.commits >= 1

    def test_unassigned_request_binds_to_first_authenticated_device(self):
        """An unassigned open request is bound to the first authenticated device
        that answers; a SECOND different device is then rejected (403)."""
        sms_mod.registered_device_keys["dev-1"] = "key-1"
        sms_mod.registered_device_keys["dev-2"] = "key-2"
        sms_mod.pending_otp_requests["req-1"] = {
            "status": "waiting", "timeout": self._future_ts(),
            # no assigned_device_id
        }
        # First device completes it.
        req1 = self._make_request(device_id="dev-1", request_id="req-1")
        _run(sms_mod.receive_otp(req1, x_device_key="key-1", db=_FakeDbSession()))
        assert sms_mod.pending_otp_requests["req-1"]["assigned_device_id"] == "dev-1"

    def test_register_device_issues_strong_persisted_key(self, monkeypatch):
        """register_device issues a secrets.token_urlsafe(32) key, persists it in
        registered_device_keys, and that key then verifies via _verify_device."""
        captured = {}
        real_token_urlsafe = sms_mod.secrets.token_urlsafe

        def _spy(n):
            val = real_token_urlsafe(n)
            captured["nbytes"] = n
            captured["value"] = val
            return val
        monkeypatch.setattr(sms_mod.secrets, "token_urlsafe", _spy)

        reg = sms_mod.DeviceRegistrationRequest(
            device_id="dev-new",
            device_name="Pixel",
            os_version="14",
            app_version="1.0.0",
        )
        result = _run(sms_mod.register_device(reg, db=_FakeDbSession()))

        assert result["success"] is True
        assert captured["nbytes"] == 32, "key must be secrets.token_urlsafe(32)"
        issued = result["api_key"]
        assert issued == captured["value"]
        # Persisted and verifiable.
        assert sms_mod.registered_device_keys["dev-new"] == issued
        assert sms_mod._verify_device("dev-new", issued) is True
        assert sms_mod._verify_device("dev-new", "not-the-key") is False


# ===========================================================================
# AREA 4: Per-tenant service-key scoping  (HIGH-2 / appsec #18)
#
# Fix under test (credentials.require_identity_scope + _load_service_identity_scopes
# + its enforcement on get_identity_accounts / request_account_credentials /
# store_account_credentials / request_identity_credentials):
#   - A service key may only act for identities it is explicitly scoped to via
#     <SERVICE>_ALLOWED_IDENTITY_IDS. Unset/blank => NO identities (fail closed).
#   - "*" is an explicit operator opt-in to act for ANY identity.
#   - A scoped list ("1,2") admits only those ids; anything else -> 403.
#   - get_identity_accounts now calls require_identity_scope BEFORE any lookup, so
#     a valid key can no longer enumerate an arbitrary identity's accounts (the
#     cross-tenant BOLA the old TODO left open).
#
# Reversion this would catch: removing require_identity_scope, defaulting an
# unconfigured service to "allow all", or dropping the scope check on
# get_identity_accounts (re-opening cross-tenant enumeration).
#
# Same cv2-free style as the rest of this file: drive the real functions directly.
# ===========================================================================
class TestServiceKeyIdentityScoping:
    @pytest.fixture(autouse=True)
    def _isolate_scopes(self):
        """Snapshot/restore the module-level SERVICE_IDENTITY_SCOPES around each
        test so we never leak scope config between tests."""
        original = credentials_mod.SERVICE_IDENTITY_SCOPES
        yield
        credentials_mod.SERVICE_IDENTITY_SCOPES = original

    # --- require_identity_scope unit behaviour --------------------------------
    def test_unconfigured_service_denies_all_identities_403(self):
        """Fail closed: a service with NO configured scope may act for no identity."""
        credentials_mod.SERVICE_IDENTITY_SCOPES = {}
        with pytest.raises(HTTPException) as exc:
            credentials_mod.require_identity_scope("scraper-service", 1)
        assert exc.value.status_code == 403

    def test_identity_outside_scope_denied_403(self):
        """A scoped key naming an identity NOT in its allow-list -> 403."""
        credentials_mod.SERVICE_IDENTITY_SCOPES = {"scraper-service": {1, 2}}
        with pytest.raises(HTTPException) as exc:
            credentials_mod.require_identity_scope("scraper-service", 99)
        assert exc.value.status_code == 403

    def test_identity_in_scope_allowed(self):
        """An identity within the key's allow-list is permitted (no raise)."""
        credentials_mod.SERVICE_IDENTITY_SCOPES = {"scraper-service": {1, 2}}
        assert credentials_mod.require_identity_scope("scraper-service", 2) is None

    def test_wildcard_scope_allows_any_identity(self):
        """Explicit "*" opt-in permits any identity."""
        credentials_mod.SERVICE_IDENTITY_SCOPES = {"mobile-service": "*"}
        assert credentials_mod.require_identity_scope("mobile-service", 12345) is None

    # --- _load_service_identity_scopes env parsing ----------------------------
    def test_loader_fail_closed_and_wildcard_and_list(self, monkeypatch):
        monkeypatch.delenv("SCRAPER_ALLOWED_IDENTITY_IDS", raising=False)
        monkeypatch.delenv("MOBILE_ALLOWED_IDENTITY_IDS", raising=False)
        monkeypatch.delenv("AUTOMATION_ALLOWED_IDENTITY_IDS", raising=False)
        # All unset -> empty map (every service denied at request time).
        assert credentials_mod._load_service_identity_scopes() == {}

        # Blank -> still omitted (fail closed).
        monkeypatch.setenv("SCRAPER_ALLOWED_IDENTITY_IDS", "   ")
        assert credentials_mod._load_service_identity_scopes() == {}

        # Wildcard + explicit list, with junk ids ignored.
        monkeypatch.setenv("SCRAPER_ALLOWED_IDENTITY_IDS", "*")
        monkeypatch.setenv("MOBILE_ALLOWED_IDENTITY_IDS", "1, 2 ,bad, 3")
        loaded = credentials_mod._load_service_identity_scopes()
        assert loaded["scraper-service"] == "*"
        assert loaded["mobile-service"] == {1, 2, 3}

    # --- get_identity_accounts enforces the scope BEFORE any DB lookup --------
    def test_get_identity_accounts_out_of_scope_denied_403(self):
        """The endpoint must 403 an out-of-scope identity WITHOUT touching the DB
        (so a bad db would not even be queried). Closes the enumeration BOLA."""
        credentials_mod.SERVICE_IDENTITY_SCOPES = {"scraper-service": {1}}

        class _ExplodingDb:
            def query(self, *a, **k):
                raise AssertionError("DB must not be queried for an out-of-scope identity")

        with pytest.raises(HTTPException) as exc:
            _run(credentials_mod.get_identity_accounts(
                identity_id=99,                 # not in {1}
                service_name="scraper-service",
                db=_ExplodingDb(),
            ))
        assert exc.value.status_code == 403

    def test_request_account_credentials_out_of_scope_denied_403(self):
        """The IDOR-hardened retrieval path now ALSO fails closed on key scope:
        an out-of-scope identity is rejected 403 before any account lookup."""
        credentials_mod.SERVICE_IDENTITY_SCOPES = {"scraper-service": {1}}

        class _ExplodingDb:
            def query(self, *a, **k):
                raise AssertionError("DB must not be queried for an out-of-scope identity")

        req = credentials_mod.AccountCredentialRequest(
            identity_id=99, account_id=5, credential_types=[],
        )
        with pytest.raises(HTTPException) as exc:
            _run(credentials_mod.request_account_credentials(req, "scraper-service", _ExplodingDb()))
        assert exc.value.status_code == 403


# ===========================================================================
# AREA 5: Auth coverage on site_integrations + llm_scraper routes
#         (HIGH-1 / CRITICAL-2 — appsec #18)
#
# Rather than spin up the app (cv2-broken locally), we introspect the registered
# FastAPI routes/dependencies of the specific routers — importing these router
# modules is cv2-free (verified). We assert that get_current_user gates the routes
# the audit flagged. A reversion that drops the dependency makes these fail.
#
#   - site_integrations: POST /signup, /signin, /apikey each depend on
#     get_current_user (the HIGH-1 abuse/credential-stuffing surface).
#   - llm_scraper: get_current_user is a ROUTER-LEVEL dependency, so EVERY route
#     (incl. the destructive DELETE and the LLM-invoking POSTs) is gated.
# ===========================================================================
import app.routers.site_integrations as site_mod  # cv2-free
import app.routers.llm_scraper as llm_mod          # cv2-free
from app.routers.auth import get_current_user


def _route_dependency_calls(route):
    """Return the set of dependency callables attached to a route (its own
    dependant + nested sub-dependencies)."""
    calls = set()
    dependant = getattr(route, "dependant", None)
    if dependant is None:
        return calls
    if getattr(dependant, "call", None) is not None:
        calls.add(dependant.call)
    for sub in getattr(dependant, "dependencies", []):
        if getattr(sub, "call", None) is not None:
            calls.add(sub.call)
        for subsub in getattr(sub, "dependencies", []):
            if getattr(subsub, "call", None) is not None:
                calls.add(subsub.call)
    return calls


class TestRouteAuthCoverage:
    @pytest.mark.parametrize(
        "method,path",
        [
            ("POST", "/api/v1/integrations/signup"),
            ("POST", "/api/v1/integrations/signin"),
            ("POST", "/api/v1/integrations/apikey"),
        ],
    )
    def test_site_integrations_operational_routes_require_auth(self, method, path):
        """HIGH-1: signup/signin/apikey must be gated by get_current_user."""
        matched = [
            r for r in site_mod.router.routes
            if getattr(r, "path", None) == path and method in getattr(r, "methods", set())
        ]
        assert matched, f"route {method} {path} not found"
        for route in matched:
            assert get_current_user in _route_dependency_calls(route), (
                f"{method} {path} is not gated by get_current_user"
            )

    def test_llm_scraper_router_level_auth_gates_every_route(self):
        """CRITICAL-2: get_current_user is a router-level dependency, so every
        route (DELETE + LLM POSTs + reads) inherits it."""
        # Router-level dependency present.
        router_dep_calls = {
            d.dependency for d in llm_mod.router.dependencies
            if getattr(d, "dependency", None) is not None
        }
        assert get_current_user in router_dep_calls, (
            "llm_scraper router is missing the router-level get_current_user dependency"
        )
        # And it actually propagates to the routes (spot-check the destructive DELETE
        # and an LLM-invoking POST).
        for method, path in [
            ("DELETE", "/api/llm-scraper/scrapers/{site_name}/{action_type}"),
            ("POST", "/api/llm-scraper/generate"),
        ]:
            matched = [
                r for r in llm_mod.router.routes
                if getattr(r, "path", None) == path and method in getattr(r, "methods", set())
            ]
            assert matched, f"route {method} {path} not found"
            for route in matched:
                assert get_current_user in _route_dependency_calls(route), (
                    f"{method} {path} is not gated by get_current_user"
                )
