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

# Test database URL
TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL", "sqlite+aiosqlite:///./test.db")

# Create test engine
test_engine = create_async_engine(TEST_DATABASE_URL, echo=False, future=True)

# Create test session maker
TestingSessionLocal = sessionmaker(
    test_engine, class_=AsyncSession, expire_on_commit=False
)


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
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """Create a test client with database session override."""

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    # base_url must present a host that TrustedHostMiddleware accepts. The app
    # allows localhost/127.0.0.1 by default; "http://test" was rejected before
    # reaching any route, so every request in this suite came back 400
    # "Invalid host header" instead of hitting the endpoint under test.
    async with AsyncClient(app=app, base_url="http://localhost") as ac:
        yield ac

    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def authed_client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """A client whose requests are already authenticated.

    Most routers depend on get_current_user, so an unauthenticated client gets
    403 from the bearer-token security scheme before the route body ever runs.
    Tests that are exercising route behaviour (rather than the auth gate itself)
    override the dependency with a fixed user. The auth gate has its own
    coverage in tests/test_security_regressions.py.
    """
    from app.models.user import User
    from app.routers.auth import get_current_user

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

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = lambda: user

    async with AsyncClient(app=app, base_url="http://localhost") as ac:
        yield ac

    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def sample_identity(db_session: AsyncSession) -> Identity:
    """Create a sample identity for testing."""
    identity = Identity(
        id="test-identity-123",
        name="Test Identity",
        email="test@example.com",
        encrypted_data=b"encrypted_test_data",
        master_key_hash="test_hash",
    )
    db_session.add(identity)
    await db_session.commit()
    await db_session.refresh(identity)
    return identity


@pytest_asyncio.fixture
async def sample_account(
    db_session: AsyncSession, sample_identity: Identity
) -> Account:
    """Create a sample account for testing."""
    account = Account(
        id="test-account-123",
        identity_id=sample_identity.id,
        site_name="test-site.com",
        username="testuser",
        encrypted_credentials=b"encrypted_test_credentials",
        status="active",
        signup_date=None,
        last_login=None,
        notes="Test account",
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
