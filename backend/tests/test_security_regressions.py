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
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from fastapi import HTTPException

# Importing these specific modules is cv2-free (verified). Importing app.main is NOT.
import app.routers.credentials as credentials_mod
import app.routers.sms as sms_mod
from app.security.fuzefront_auth import Identity as DelegatedIdentity

DELEGATED = DelegatedIdentity(
    subject="owner",
    tenant_id="tenant-1",
    scopes=frozenset({"connectors:credentials:read", "connectors:credentials:write"}),
    audience="service:fuzekeys",
    actor={"sub": "service:scraper"},
    token_kind="fuze-delegation",
)


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
        assert (
            _run(credentials_mod.verify_api_key(x_api_key="scraper-secret"))
            == "scraper-service"
        )
        assert (
            _run(credentials_mod.verify_api_key(x_api_key="mobile-secret"))
            == "mobile-service"
        )

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

        assert (
            _run(credentials_mod.verify_api_key(x_api_key="env-only-key"))
            == "scraper-service"
        )
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
# store_account_credentials) against a real (in-memory SQLite) asynchronous
# SQLAlchemy session, seeding two identities owned by different users, each with
# its own account. We stub verify_api_key out by passing service_name directly
# (the handlers take service_name as a plain arg), so this isolates the
# ownership-scoping logic under test.
#
# Reversion this would catch: removing the `Account.identity_id == identity_id`
# filter (i.e. looking up by account_id alone), which is the IDOR.
# ===========================================================================
@pytest.mark.asyncio
class TestIdorOwnershipScoping:
    @pytest.fixture(autouse=True)
    def _allow_platform_decision(self, monkeypatch):
        """Isolate the SQL identity/account predicate from platform decisions."""
        monkeypatch.setattr(
            credentials_mod, "require_delegated_owner_permission", AsyncMock()
        )

    @pytest_asyncio.fixture
    async def db_session(self):
        """An asynchronous in-memory SQLite session with the User/Identity/Account
        tables created. Uses the app's real ORM models so the scoping query the
        endpoint runs is exercised verbatim."""
        from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

        from app.database import Base
        from app.models.account import Account
        from app.models.identity import Identity
        from app.models.user import User

        engine = create_async_engine("sqlite+aiosqlite://")
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        try:
            async with AsyncSession(engine, expire_on_commit=False) as session:
                yield session, User, Identity, Account
        finally:
            await engine.dispose()

    @staticmethod
    async def _seed_two_tenants(session, User, Identity, Account):
        """Create two users, each with one identity owning one account."""
        user_a = User(
            email="<EMAIL_a>",
            username="user_a",
            hashed_password="h",
            master_key_hash="m",
        )
        user_b = User(
            email="<EMAIL_b>",
            username="user_b",
            hashed_password="h",
            master_key_hash="m",
        )
        session.add_all([user_a, user_b])
        await session.flush()

        identity_a = Identity(user_id=user_a.id, name="Identity A")
        identity_b = Identity(user_id=user_b.id, name="Identity B")
        session.add_all([identity_a, identity_b])
        await session.flush()

        account_a = Account(
            identity_id=identity_a.id,
            website_name="SiteA",
            website_url="https://a.example",
            encrypted_credentials=None,
        )
        account_b = Account(
            identity_id=identity_b.id,
            website_name="SiteB",
            website_url="https://b.example",
            encrypted_credentials=None,
        )
        session.add_all([account_a, account_b])
        await session.commit()
        return identity_a, identity_b, account_a, account_b

    async def test_retrieve_with_wrong_owning_identity_yields_404(self, db_session):
        """IDOR core: account_b belongs to identity_b. A request for account_b
        that names identity_a (a different owner) must 404 — no cross-tenant data."""
        session, User, Identity, Account = db_session
        identity_a, identity_b, account_a, account_b = await self._seed_two_tenants(
            session, User, Identity, Account
        )

        req = credentials_mod.AccountCredentialRequest(
            identity_id=identity_a.id,  # WRONG owner for account_b
            account_id=account_b.id,
            credential_types=[],
        )
        with pytest.raises(HTTPException) as exc:
            await credentials_mod.request_account_credentials(req, DELEGATED, session)
        assert exc.value.status_code == 404

    async def test_retrieve_with_correct_owner_succeeds(self, db_session):
        """The legitimate path: correct (identity, account) pair returns the
        account (200), proving the 404 above is the scoping check, not a blanket deny.
        """
        session, User, Identity, Account = db_session
        identity_a, identity_b, account_a, account_b = await self._seed_two_tenants(
            session, User, Identity, Account
        )

        req = credentials_mod.AccountCredentialRequest(
            identity_id=identity_b.id,  # correct owner of account_b
            account_id=account_b.id,
            credential_types=[],
        )
        resp = await credentials_mod.request_account_credentials(
            req, DELEGATED, session
        )
        assert resp.account_id == account_b.id
        assert resp.site_name == "SiteB"

    async def test_store_with_wrong_owning_identity_yields_404_and_no_mutation(
        self, db_session, monkeypatch
    ):
        """Store path enforces the same scoping AND does not mutate the victim's
        account when the wrong owner is named."""
        session, User, Identity, Account = db_session
        identity_a, identity_b, account_a, account_b = await self._seed_two_tenants(
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
            identity_id=identity_a.id,  # WRONG owner for account_b
            account_id=account_b.id,
            credentials={"password": "attacker-write"},
            metadata=None,
        )
        with pytest.raises(HTTPException) as exc:
            await credentials_mod.store_account_credentials(req, DELEGATED, session)
        assert exc.value.status_code == 404

        await session.refresh(account_b)
        refreshed = account_b
        assert (
            refreshed.encrypted_credentials == before
        ), "victim account must not be mutated"
        assert refreshed.encrypted_credentials is None

    async def test_store_with_correct_owner_succeeds(self, db_session, monkeypatch):
        """Legitimate store with the correct owner persists encrypted credentials."""
        session, User, Identity, Account = db_session
        identity_a, identity_b, account_a, account_b = await self._seed_two_tenants(
            session, User, Identity, Account
        )
        from cryptography.fernet import Fernet

        valid_key = Fernet.generate_key().decode()
        monkeypatch.setattr(credentials_mod, "ENCRYPTION_KEY", valid_key)

        req = credentials_mod.CredentialUpdate(
            identity_id=identity_b.id,  # correct owner
            account_id=account_b.id,
            credentials={"password": "legit"},
            metadata=None,
        )
        result = await credentials_mod.store_account_credentials(
            req, DELEGATED, session
        )
        assert result["success"] is True
        await session.refresh(account_b)
        refreshed = account_b
        assert refreshed.encrypted_credentials is not None


# ===========================================================================
# Durable SMS principal, assignment, restart and creator-isolation coverage lives
# in test_sms_request_isolation.py and exercises the real AsyncSession path.
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

    # The parser/constant-time unit contract remains for compatibility, but the
    # mounted credential routes deliberately no longer accept this legacy proof.
    def test_static_service_key_is_not_a_mounted_credential_dependency(self):
        for route in credentials_mod.router.routes:
            if route.path == "/api/credentials/health":
                continue
            calls = {
                dependency.call
                for dependency in route.dependant.dependencies
                if dependency.call is not None
            }
            assert credentials_mod.verify_api_key not in calls


import app.routers.llm_scraper as llm_mod  # cv2-free

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
            r
            for r in site_mod.router.routes
            if getattr(r, "path", None) == path
            and method in getattr(r, "methods", set())
        ]
        assert matched, f"route {method} {path} not found"
        for route in matched:
            assert get_current_user in _route_dependency_calls(
                route
            ), f"{method} {path} is not gated by get_current_user"

    def test_llm_scraper_router_level_auth_gates_every_route(self):
        """CRITICAL-2: get_current_user is a router-level dependency, so every
        route (DELETE + LLM POSTs + reads) inherits it."""
        # Router-level dependency present.
        router_dep_calls = {
            d.dependency
            for d in llm_mod.router.dependencies
            if getattr(d, "dependency", None) is not None
        }
        assert (
            get_current_user in router_dep_calls
        ), "llm_scraper router is missing the router-level get_current_user dependency"
        # And it actually propagates to the routes (spot-check the destructive DELETE
        # and an LLM-invoking POST).
        for method, path in [
            ("DELETE", "/api/llm-scraper/scrapers/{site_name}/{action_type}"),
            ("POST", "/api/llm-scraper/generate"),
        ]:
            matched = [
                r
                for r in llm_mod.router.routes
                if getattr(r, "path", None) == path
                and method in getattr(r, "methods", set())
            ]
            assert matched, f"route {method} {path} not found"
            for route in matched:
                assert get_current_user in _route_dependency_calls(
                    route
                ), f"{method} {path} is not gated by get_current_user"
