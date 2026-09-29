"""Provider-scoped credential custody must preserve the Gmail compatibility URL."""

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.routers import connectors


def test_provider_ids_cannot_escape_vault_namespace():
    for invalid in ("../other", "google/gmail", "Google-Gmail", "a--b", "a%2fb", "", "a" * 81):
        with pytest.raises(HTTPException) as exc:
            connectors._provider(invalid)
        assert exc.value.status_code == 422
    assert connectors._provider("microsoft-outlook") == "microsoft-outlook"


def test_gmail_routes_precede_generic_routes():
    paths = [route.path for route in connectors.router.routes]
    for method_path in ("", "/credential"):
        assert paths.index("/api/v1/connectors/google-gmail" + method_path) < paths.index(
            "/api/v1/connectors/{provider}" + method_path
        )


@pytest.mark.asyncio
async def test_credential_keys_are_scoped_by_owner_and_provider(monkeypatch):
    rows = {}
    secrets = {}

    async def record(db, owner, provider):
        return rows.get((owner, provider))

    class Session:
        def add(self, row):
            rows[(row.owner_subject, row.provider)] = row

        async def commit(self):
            pass

    class Vault:
        def put(self, key, data):
            secrets[key] = data

        def load_root(self, key):
            return secrets.get(key)

    monkeypatch.setattr(connectors, "_record", record)
    monkeypatch.setattr(connectors, "_vault", lambda: Vault())
    session = Session()
    for owner, provider in (("person/a", "google-gmail"), ("person/a", "microsoft-outlook"), ("person/b", "google-gmail")):
        await connectors.update_credential(
            connectors.CredentialUpdate(credential={"token": provider + owner}),
            provider,
            SimpleNamespace(subject=owner),
            session,
        )
    assert len(secrets) == 3
    assert all(key.startswith("connectors/person%2F") for key in secrets)
    result = await connectors.lease_credential(
        "microsoft-outlook", SimpleNamespace(subject="person/a"), session
    )
    assert result["credential"] == {"token": "microsoft-outlookperson/a"}
