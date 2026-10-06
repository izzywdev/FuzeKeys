"""Provider-scoped credential custody must preserve the Gmail compatibility URL."""

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.routers import connectors


def test_provider_ids_cannot_escape_vault_namespace():
    for invalid in (
        "../other",
        "google/gmail",
        "Google-Gmail",
        "a--b",
        "a%2fb",
        "",
        "a" * 81,
    ):
        with pytest.raises(HTTPException) as exc:
            connectors._provider(invalid)
        assert exc.value.status_code == 422
    assert connectors._provider("microsoft-outlook") == "microsoft-outlook"


def test_gmail_routes_precede_generic_routes():
    paths = [route.path for route in connectors.router.routes]
    for method_path in ("", "/credential"):
        assert paths.index(
            "/api/v1/connectors/google-gmail" + method_path
        ) < paths.index("/api/v1/connectors/{provider}" + method_path)


@pytest.mark.asyncio
async def test_credential_keys_are_scoped_by_tenant_owner_and_provider(monkeypatch):
    from unittest.mock import AsyncMock

    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    from app.broker.vault import InMemoryVault
    from app.models.connector import ConnectorCredential, ConnectorGrantIntent
    from app.security import connector_authz

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(ConnectorCredential.__table__.create)
        await conn.run_sync(ConnectorGrantIntent.__table__.create)
    vault = InMemoryVault()
    monkeypatch.setattr(connectors, "_vault", lambda: vault)
    monkeypatch.setattr(
        connector_authz, "check_permission", AsyncMock(return_value=True)
    )
    try:
        async with AsyncSession(engine, expire_on_commit=False) as session:
            for tenant, owner, provider in (
                ("tenant/a", "person/a", "slack"),
                ("tenant/a", "person/a", "microsoft-outlook"),
                ("tenant/a", "person/b", "slack"),
                ("tenant/b", "person/a", "slack"),
            ):
                identity = SimpleNamespace(subject=owner, tenant_id=tenant)
                body = connectors.CredentialUpdate(
                    credential={"token": tenant + owner + provider}
                )
                staged = await connectors.update_credential(
                    body, provider, identity, session
                )
                assert staged.status_code == 202
                await connectors.update_credential(body, provider, identity, session)
            for tenant, owner, provider in (
                ("tenant/a", "person/a", "slack"),
                ("tenant/a", "person/a", "microsoft-outlook"),
                ("tenant/a", "person/b", "slack"),
                ("tenant/b", "person/a", "slack"),
            ):
                result = await connectors.lease_credential(
                    provider, SimpleNamespace(subject=owner, tenant_id=tenant), session
                )
                assert result["credential"] == {"token": tenant + owner + provider}
                assert (
                    vault.load_root(connectors._connector_ref(tenant, owner, provider))
                    is not None
                )
    finally:
        await engine.dispose()
