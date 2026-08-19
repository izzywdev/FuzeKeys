"""
Pytest configuration and fixtures for FuzeKeys backend tests.
"""

import asyncio
import os
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

# NOTE: app.database exposes the async dependency as `get_async_session` with a
# backward-compat alias `get_db` (it does NOT export `get_db_session`). The
# routers all declare `Depends(get_db)`, so `get_db` is the correct symbol to
# import and to use as the dependency-override key.
from app.database import Base, get_db
from app.main import app
from app.models.account import Account
from app.models.identity import Identity
from app.models.user import User
from app.utils import encryption as encryption_module
from app.utils.encryption import encrypt_field, set_global_encryption_manager

# Test database URL
TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL", "sqlite+aiosqlite:///./test.db")

# The master key the suite encrypts/decrypts identity and account fields with.
# Any non-empty string works -- the value only has to be stable within a run so
# that encrypt_field() and decrypt_field() agree.
TEST_MASTER_KEY = "test-master-key"

# Base URL for every test client. TrustedHostMiddleware only allows
# localhost/127.0.0.1; httpx's default ("http://test") and TestClient's default
# ("http://testserver") are both rejected with 400 "Invalid host header" before
# any route runs, so every request would come back 400 instead of hitting the
# endpoint under test.
TEST_BASE_URL = "http://localhost"

# Create test engine
test_engine = create_async_engine(TEST_DATABASE_URL, echo=False, future=True)

# Create test session maker
TestingSessionLocal = sessionmaker(
    test_engine, class_=AsyncSession, expire_on_commit=False
)


@pytest.fixture(autouse=True)
def encryption_manager(setup_test_env):
    """Initialise the process-global encryption manager for every test.

    `encrypt_field` / `decrypt_field` raise ValueError("Encryption manager not
    initialized") when the global manager is unset, and the routers wrap their
    bodies in `except Exception` -> HTTP 500. In production the manager is set
    by the login route (app/routers/auth.py); tests that bypass login by
    overriding get_current_user have to stand it up themselves or every
    identity/account request 500s for a reason that has nothing to do with the
    behaviour under test.

    Depends on `setup_test_env` because EncryptionManager reads MASTER_KEY_SALT
    at construction time -- deriving the key before the salt is pinned would
    make the derived Fernet key depend on whatever ran previously.

    The previous value is restored afterwards so the fixture is hermetic.
    """
    previous = encryption_module._global_encryption_manager
    set_global_encryption_manager(TEST_MASTER_KEY)
    yield encryption_module.get_global_encryption_manager()
    encryption_module._global_encryption_manager = previous


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Create a test database session."""
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with TestingSessionLocal() as session:
        yield session

    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def test_user(db_session: AsyncSession) -> User:
    """The user that `authed_client` authenticates as.

    Exposed separately so a test can assert ownership scoping -- e.g. that an
    identity belonging to a *different* user is invisible.
    """
    user = User(
        username="testuser",
        email="testuser@example.com",
        hashed_password="not-a-real-hash",
        master_key_hash="not-a-real-master-key-hash",
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """Create a test client with database session override."""

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(app=app, base_url=TEST_BASE_URL) as ac:
        yield ac

    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def authed_client(
    db_session: AsyncSession, test_user: User
) -> AsyncGenerator[AsyncClient, None]:
    """A client whose requests are already authenticated.

    Most routers depend on get_current_user, so an unauthenticated client gets
    403 from the bearer-token security scheme before the route body ever runs.
    Tests that are exercising route behaviour (rather than the auth gate itself)
    override the dependency with a fixed user. The auth gate has its own
    coverage in tests/test_security_regressions.py.
    """
    from app.routers.auth import get_current_user

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = lambda: test_user

    async with AsyncClient(app=app, base_url=TEST_BASE_URL) as ac:
        yield ac

    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def sample_identity(db_session: AsyncSession, test_user: User) -> Identity:
    """A persisted Identity owned by `test_user`.

    PII lives in encrypted_* columns, so the fixture writes through
    encrypt_field() rather than assigning plaintext -- otherwise the router's
    decrypt on read fails and the endpoint 500s.
    """
    identity = Identity(
        user_id=test_user.id,
        name="Test Identity",
        description="Identity used by the API tests",
        encrypted_first_name=encrypt_field("Test"),
        encrypted_last_name=encrypt_field("Person"),
        encrypted_email=encrypt_field("test@example.com"),
        encrypted_phone=encrypt_field("+15555550100"),
    )
    db_session.add(identity)
    await db_session.commit()
    await db_session.refresh(identity)
    return identity


@pytest_asyncio.fixture
async def sample_account(
    db_session: AsyncSession, sample_identity: Identity
) -> Account:
    """A persisted Account hanging off `sample_identity`."""
    account = Account(
        identity_id=sample_identity.id,
        website_name="Test Site",
        website_url="https://test-site.com",
        website_domain="test-site.com",
        encrypted_username=encrypt_field("testuser"),
        encrypted_email=encrypt_field("test@example.com"),
        account_type="free",
        signup_method="manual",
        is_active=True,
        signup_completed=False,
    )
    db_session.add(account)
    await db_session.commit()
    await db_session.refresh(account)
    return account


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


# Test configuration
@pytest.fixture(autouse=True)
def setup_test_env():
    """Setup test environment variables."""
    os.environ.update(
        {
            "ENVIRONMENT": "test",
            "SECRET_KEY": "test-secret-key",
            "MASTER_KEY_SALT": "test-salt",
            "DATABASE_URL_ASYNC": TEST_DATABASE_URL,
        }
    )
