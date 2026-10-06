"""Proof boundaries, immutable bindings, and database race constraints."""

import httpx
import pytest
from sqlalchemy import select

from app.models.platform_identity import PlatformIdentity
from app.models.user import User
from app.routers import platform_identity as routes
from app.security import platform_identity as verifier
from app.security.platform_authz import PlatformAuthorizationUnavailable


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "body,status,expected",
    [
        (
            {"identity": {"userId": "trusted-user", "tenantId": "tenant-1"}},
            200,
            "allow",
        ),
        ({"identity": {"userId": "trusted-user", "tenantId": None}}, 200, "reject"),
        (
            {"identity": {"userId": "trusted-user", "tenantId": "tenant-2"}},
            200,
            "reject",
        ),
        ({"identity": {"userId": 7, "tenantId": "tenant-1"}}, 200, "unavailable"),
        ({}, 401, "reject"),
        ({}, 403, "reject"),
        ({}, 503, "unavailable"),
        ({}, 302, "unavailable"),
    ],
)
async def test_verifies_session_and_canonical_membership(
    monkeypatch, body, status, expected
):
    monkeypatch.setenv("FUZEFRONT_SECURITY_URL", "http://security.internal:3002")
    monkeypatch.setenv("FUZEKEYS_AUTHZ_TENANT", "tenant-1")
    calls = []

    def handler(request):
        calls.append(request)
        assert request.headers["Authorization"] == "Bearer platform-session"
        assert request.url.host == "security.internal"
        assert request.url.path == "/api/v1/security/session"
        assert request.url.params["tenant"] == "tenant-1"
        return httpx.Response(status, json=body)

    real_client = httpx.AsyncClient

    def client(**kwargs):
        assert kwargs["follow_redirects"] is False
        assert kwargs["timeout"] == 3.0
        return real_client(transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr(verifier.httpx, "AsyncClient", client)
    if expected == "allow":
        assert await verifier.verify_platform_identity("platform-session") == (
            "trusted-user",
            "tenant-1",
        )
        assert len(calls) == 1
    else:
        exception = (
            verifier.PlatformIdentityRejected
            if expected == "reject"
            else PlatformAuthorizationUnavailable
        )
        with pytest.raises(exception):
            await verifier.verify_platform_identity("platform-session")


@pytest.mark.asyncio
async def test_link_is_idempotent_immutable_and_does_not_store_tokens(
    authed_client, db_session, test_user, monkeypatch
):
    pair = ["trusted-user", "tenant-1"]

    async def verify(token):
        assert token == "platform-session"
        return tuple(pair)

    monkeypatch.setattr(routes, "verify_platform_identity", verify)
    headers = {"X-FuzeFront-Session": "platform-session"}
    for _ in range(2):
        response = await authed_client.post(
            "/api/v1/auth/platform-link", headers=headers
        )
        assert response.status_code == 200
        assert response.json() == {"subject": "trusted-user", "tenant": "tenant-1"}
    pair[0] = "different-user"
    response = await authed_client.post("/api/v1/auth/platform-link", headers=headers)
    assert response.status_code == 409
    rows = (await db_session.execute(select(PlatformIdentity))).scalars().all()
    assert len(rows) == 1
    assert rows[0].user_id == test_user.id
    assert rows[0].subject == "trusted-user"
    assert "token" not in PlatformIdentity.__table__.columns


@pytest.mark.asyncio
async def test_platform_pair_cannot_link_to_two_local_users(
    authed_client, db_session, monkeypatch
):
    other = User(
        username="other",
        email="other@example.com",
        hashed_password="unused",
        master_key_hash="unused",
        is_active=True,
    )
    db_session.add(other)
    await db_session.flush()
    db_session.add(
        PlatformIdentity(user_id=other.id, subject="trusted-user", tenant="tenant-1")
    )
    await db_session.commit()

    async def verify(token):
        return "trusted-user", "tenant-1"

    monkeypatch.setattr(routes, "verify_platform_identity", verify)
    response = await authed_client.post(
        "/api/v1/auth/platform-link",
        headers={"X-FuzeFront-Session": "platform-session"},
    )
    assert response.status_code == 409
    assert "other" not in response.text


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error,status",
    [(verifier.PlatformIdentityRejected, 403), (PlatformAuthorizationUnavailable, 503)],
)
async def test_failed_verification_persists_nothing(
    authed_client, db_session, monkeypatch, error, status
):
    async def verify(token):
        raise error("sensitive upstream diagnostic")

    monkeypatch.setattr(routes, "verify_platform_identity", verify)
    response = await authed_client.post(
        "/api/v1/auth/platform-link",
        headers={"X-FuzeFront-Session": "platform-session"},
    )
    assert response.status_code == status
    assert "sensitive" not in response.text
    assert (await db_session.execute(select(PlatformIdentity))).first() is None


@pytest.mark.asyncio
async def test_local_session_alone_cannot_link(authed_client):
    response = await authed_client.post("/api/v1/auth/platform-link")
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_platform_session_alone_cannot_link(client):
    response = await client.post(
        "/api/v1/auth/platform-link",
        headers={"X-FuzeFront-Session": "platform-session"},
    )
    assert response.status_code in (401, 403)


@pytest.mark.asyncio
async def test_inactive_local_user_cannot_link(authed_client, test_user, monkeypatch):
    test_user.is_active = False

    async def verify(token):
        pytest.fail("Inactive local users must be rejected before verification")

    monkeypatch.setattr(routes, "verify_platform_identity", verify)
    response = await authed_client.post(
        "/api/v1/auth/platform-link",
        headers={"X-FuzeFront-Session": "platform-session"},
    )
    assert response.status_code == 403


def test_interactive_link_is_excluded_from_generated_tools():
    from app.main import app

    assert "/api/v1/auth/platform-link" not in app.openapi()["paths"]


def test_binding_migration_preserves_existing_users_on_upgrade_and_downgrade():
    import importlib.util
    from pathlib import Path

    import sqlalchemy as sa

    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    source = (
        Path(__file__).parents[1]
        / "alembic/versions/b2026link01_platform_identities.py"
    )
    spec = importlib.util.spec_from_file_location("binding_migration", source)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    engine = sa.create_engine("sqlite://")
    with engine.begin() as connection:
        connection.execute(sa.text("CREATE TABLE users (id INTEGER PRIMARY KEY)"))
        connection.execute(sa.text("INSERT INTO users (id) VALUES (7)"))
        with Operations.context(MigrationContext.configure(connection)):
            migration.upgrade()
            assert "platform_identities" in sa.inspect(connection).get_table_names()
            migration.downgrade()
            assert "platform_identities" not in sa.inspect(connection).get_table_names()
        assert connection.execute(sa.text("SELECT id FROM users")).scalar() == 7
