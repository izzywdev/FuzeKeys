"""
Pytest configuration and fixtures for FuzeKeys backend tests.
"""

import asyncio
import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from app.main import app
from app.database import get_db_session, Base
from app.models.identity import Identity
from app.models.account import Account
import os
from typing import AsyncGenerator

# Test database URL
TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL", 
    "sqlite+aiosqlite:///./test.db"
)

# Create test engine
test_engine = create_async_engine(
    TEST_DATABASE_URL,
    echo=False,
    future=True
)

# Create test session maker
TestingSessionLocal = sessionmaker(
    test_engine, 
    class_=AsyncSession, 
    expire_on_commit=False
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
    
    app.dependency_overrides[get_db_session] = override_get_db
    
    async with AsyncClient(app=app, base_url="http://test") as ac:
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
        master_key_hash="test_hash"
    )
    db_session.add(identity)
    await db_session.commit()
    await db_session.refresh(identity)
    return identity

@pytest_asyncio.fixture
async def sample_account(db_session: AsyncSession, sample_identity: Identity) -> Account:
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
        notes="Test account"
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
    os.environ.update({
        "ENVIRONMENT": "test",
        "SECRET_KEY": "test-secret-key",
        "MASTER_KEY_SALT": "test-salt",
        "DATABASE_URL_ASYNC": TEST_DATABASE_URL,
    }) 