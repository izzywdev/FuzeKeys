"""
Tests for the identities API endpoints (`/api/v1/identities`).

This suite replaces one that was written against a superseded, plaintext-PII
identity API: it asserted flat `email`/`phone`/`address` columns and string
primary keys, and called the un-versioned `/api/identities`. None of that
matches the shipped model (encrypted_* columns, integer id, required user_id
owner) or the mounted prefix, so the whole file was quarantined behind a
module-level skip.

What is covered here is the API as it actually is: create/list/get/update/
delete under `/api/v1/identities`, the ownership boundary, and the round-trip
through the encrypted columns.
"""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.identity import Identity
from app.models.user import User

BASE = "/api/v1/identities"

NEW_IDENTITY = {
    "name": "Work Persona",
    "description": "Used for professional signups",
    "first_name": "Ada",
    "last_name": "Lovelace",
    "email": "ada@example.com",
    "phone": "+15555550111",
    "city": "London",
    "country": "UK",
    "profession": "Mathematician",
}


class TestIdentitiesAPI:
    """CRUD behaviour of the identities router."""

    @pytest.mark.asyncio
    async def test_list_identities_empty(self, authed_client: AsyncClient):
        """A user with no identities gets an empty list, not a 404."""
        response = await authed_client.get(f"{BASE}/")
        assert response.status_code == 200
        assert response.json() == []

    @pytest.mark.asyncio
    async def test_list_identities_with_data(
        self, authed_client: AsyncClient, sample_identity: Identity
    ):
        """The list view returns the summary shape, not the decrypted PII."""
        response = await authed_client.get(f"{BASE}/")
        assert response.status_code == 200

        data = response.json()
        assert len(data) == 1

        item = data[0]
        assert item["id"] == sample_identity.id
        assert item["name"] == "Test Identity"
        assert item["description"] == "Identity used by the API tests"

        # IdentityListResponse deliberately carries no PII. Guard that, so a
        # future widening of the list model is a failing test rather than a
        # silent broadening of what a list call leaks.
        assert set(item) == {"id", "name", "description", "created_at"}

    @pytest.mark.asyncio
    async def test_create_identity(self, authed_client: AsyncClient):
        """POST returns the decrypted view of what it just stored."""
        response = await authed_client.post(f"{BASE}/", json=NEW_IDENTITY)
        assert response.status_code == 200

        data = response.json()
        assert isinstance(data["id"], int)
        assert data["name"] == "Work Persona"
        assert data["first_name"] == "Ada"
        assert data["last_name"] == "Lovelace"
        assert data["email"] == "ada@example.com"
        assert data["phone"] == "+15555550111"
        assert data["city"] == "London"
        assert data["profession"] == "Mathematician"
        # Not supplied in the request -> absent, not empty-string.
        assert data["company"] is None

    @pytest.mark.asyncio
    async def test_create_identity_persists_pii_encrypted(
        self, authed_client: AsyncClient, db_session: AsyncSession
    ):
        """The PII must not be readable from the row itself.

        This is the invariant the whole product rests on: the API hands back
        plaintext, the table holds ciphertext.
        """
        response = await authed_client.post(f"{BASE}/", json=NEW_IDENTITY)
        assert response.status_code == 200
        identity_id = response.json()["id"]

        stored = await db_session.get(Identity, identity_id)
        assert stored is not None

        assert stored.encrypted_email is not None
        assert stored.encrypted_email != "ada@example.com"
        assert "ada@example.com" not in stored.encrypted_email
        assert stored.encrypted_last_name != "Lovelace"
        assert "Lovelace" not in stored.encrypted_last_name

        # Non-sensitive metadata is stored in the clear by design.
        assert stored.name == "Work Persona"

    @pytest.mark.asyncio
    async def test_create_identity_assigns_current_user_as_owner(
        self, authed_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        """user_id comes from the token, never from the request body."""
        response = await authed_client.post(
            f"{BASE}/", json={**NEW_IDENTITY, "user_id": 9999}
        )
        assert response.status_code == 200

        stored = await db_session.get(Identity, response.json()["id"])
        assert stored.user_id == test_user.id

    @pytest.mark.asyncio
    async def test_create_identity_rejects_invalid_email(
        self, authed_client: AsyncClient
    ):
        """`email` is an EmailStr, so a malformed address is a 422."""
        response = await authed_client.post(
            f"{BASE}/", json={**NEW_IDENTITY, "email": "not-an-email"}
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_create_identity_requires_name(self, authed_client: AsyncClient):
        """`name` has no default, so omitting it is a 422."""
        payload = {k: v for k, v in NEW_IDENTITY.items() if k != "name"}
        response = await authed_client.post(f"{BASE}/", json=payload)
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_get_identity(
        self, authed_client: AsyncClient, sample_identity: Identity
    ):
        """GET by id decrypts the stored fields back to plaintext."""
        response = await authed_client.get(f"{BASE}/{sample_identity.id}")
        assert response.status_code == 200

        data = response.json()
        assert data["id"] == sample_identity.id
        assert data["first_name"] == "Test"
        assert data["last_name"] == "Person"
        assert data["email"] == "test@example.com"
        assert data["phone"] == "+15555550100"

    @pytest.mark.asyncio
    async def test_get_identity_not_found(self, authed_client: AsyncClient):
        """An id that does not exist is a 404."""
        response = await authed_client.get(f"{BASE}/999999")
        assert response.status_code == 404
        assert response.json()["detail"] == "Identity not found"

    @pytest.mark.asyncio
    async def test_get_identity_owned_by_another_user_is_404(
        self, authed_client: AsyncClient, db_session: AsyncSession
    ):
        """Another user's identity is invisible, and indistinguishable from absent.

        The query filters on user_id as well as id, so the response is 404
        rather than 403 -- a 403 would confirm the row exists.
        """
        other_user = User(
            username="otheruser",
            email="other@example.com",
            hashed_password="not-a-real-hash",
            master_key_hash="not-a-real-master-key-hash",
            is_active=True,
        )
        db_session.add(other_user)
        await db_session.commit()
        await db_session.refresh(other_user)

        foreign = Identity(user_id=other_user.id, name="Not Yours")
        db_session.add(foreign)
        await db_session.commit()
        await db_session.refresh(foreign)

        response = await authed_client.get(f"{BASE}/{foreign.id}")
        assert response.status_code == 404

        # ...and it does not leak through the list view either.
        listed = await authed_client.get(f"{BASE}/")
        assert listed.status_code == 200
        assert listed.json() == []

    @pytest.mark.asyncio
    async def test_update_identity(
        self, authed_client: AsyncClient, sample_identity: Identity
    ):
        """PUT applies only the supplied fields and leaves the rest alone."""
        response = await authed_client.put(
            f"{BASE}/{sample_identity.id}",
            json={"name": "Renamed", "city": "Berlin"},
        )
        assert response.status_code == 200

        data = response.json()
        assert data["name"] == "Renamed"
        assert data["city"] == "Berlin"
        # Untouched fields survive the partial update.
        assert data["email"] == "test@example.com"
        assert data["last_name"] == "Person"

    @pytest.mark.asyncio
    async def test_update_identity_reencrypts(
        self,
        authed_client: AsyncClient,
        db_session: AsyncSession,
        sample_identity: Identity,
    ):
        """An updated PII field is re-encrypted, not written through in the clear."""
        response = await authed_client.put(
            f"{BASE}/{sample_identity.id}", json={"email": "moved@example.com"}
        )
        assert response.status_code == 200
        assert response.json()["email"] == "moved@example.com"

        await db_session.refresh(sample_identity)
        assert "moved@example.com" not in sample_identity.encrypted_email

    @pytest.mark.asyncio
    async def test_update_identity_not_found(self, authed_client: AsyncClient):
        response = await authed_client.put(f"{BASE}/999999", json={"name": "Nope"})
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_identity(
        self,
        authed_client: AsyncClient,
        db_session: AsyncSession,
        sample_identity: Identity,
    ):
        """DELETE removes the row and the identity stops being listed."""
        identity_id = sample_identity.id

        response = await authed_client.delete(f"{BASE}/{identity_id}")
        assert response.status_code == 200
        assert response.json() == {"message": "Identity deleted successfully"}

        assert await db_session.get(Identity, identity_id) is None

        follow_up = await authed_client.get(f"{BASE}/{identity_id}")
        assert follow_up.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_identity_not_found(self, authed_client: AsyncClient):
        response = await authed_client.delete(f"{BASE}/999999")
        assert response.status_code == 404


class TestIdentitiesRouting:
    """The prefix itself, which is what #80 turned out to be about."""

    @pytest.mark.asyncio
    async def test_unversioned_path_is_not_served(self, authed_client: AsyncClient):
        """`/api/identities` must not exist.

        The frontend used to call exactly this and got a 404 in production.
        Asserting the *absence* keeps a well-meaning compatibility alias from
        quietly reintroducing an un-versioned surface, which gate-api-version
        now forbids.
        """
        response = await authed_client.get("/api/identities")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_requires_authentication(self, client: AsyncClient):
        """Without a bearer token the router is closed."""
        response = await client.get(f"{BASE}/")
        assert response.status_code in (401, 403)
