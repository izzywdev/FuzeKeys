"""
Tests for the accounts API endpoints (`/api/v1/accounts`).

This suite replaces one written against a superseded Account schema -- it used
`site_name`/`status`/`notes` with string primary keys and called the
un-versioned `/api/accounts`, while the shipped model has
`website_name`/`website_url` plus encrypted_* columns with integer ids behind
`get_current_user`. The whole file was quarantined behind a module-level skip.

Covered here: list/create, the stage machinery `create_account` sets up, the
PATCH stage transition, and the ownership boundary (accounts reach the current
user only through their identity).
"""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.models.account import Account, AccountStage, StageStatus
from app.models.identity import Identity
from app.models.user import User

BASE = "/api/v1/accounts"

# create_account always seeds these four; a handful of sites get extras.
COMMON_STAGE_NAMES = {
    "Email Verification",
    "Profile Setup",
    "Terms Acceptance",
    "Account Activation",
}


def new_account_payload(identity_id: int, **overrides) -> dict:
    payload = {
        "website_name": "Example",
        "website_url": "https://www.example.com/signup",
        "identity_id": identity_id,
    }
    payload.update(overrides)
    return payload


class TestAccountsAPI:
    """List and create."""

    @pytest.mark.asyncio
    async def test_list_accounts_empty(self, authed_client: AsyncClient):
        response = await authed_client.get(f"{BASE}/")
        assert response.status_code == 200
        assert response.json() == []

    @pytest.mark.asyncio
    async def test_list_accounts_with_data(
        self, authed_client: AsyncClient, sample_account: Account
    ):
        """The list joins through Identity to reach the current user."""
        response = await authed_client.get(f"{BASE}/")
        assert response.status_code == 200

        data = response.json()
        assert len(data) == 1

        item = data[0]
        assert item["id"] == sample_account.id
        assert item["website_name"] == "Test Site"
        assert item["website_url"] == "https://test-site.com"
        assert item["identity_id"] == sample_account.identity_id
        assert item["identity_name"] == "Test Identity"
        assert item["is_active"] is True
        assert item["signup_completed"] is False
        # sample_account is created directly, so it has no seeded stages.
        assert item["stages"] == []

    @pytest.mark.asyncio
    async def test_create_account(
        self, authed_client: AsyncClient, sample_identity: Identity
    ):
        response = await authed_client.post(
            f"{BASE}/", json=new_account_payload(sample_identity.id)
        )
        assert response.status_code == 200

        data = response.json()
        assert isinstance(data["id"], int)
        assert data["website_name"] == "Example"
        assert data["identity_id"] == sample_identity.id
        assert data["identity_name"] == "Test Identity"
        assert data["is_active"] is True
        assert data["signup_completed"] is False

    @pytest.mark.asyncio
    async def test_create_account_seeds_default_stages(
        self, authed_client: AsyncClient, sample_identity: Identity
    ):
        """Every new account starts with the four common stages, all pending."""
        response = await authed_client.post(
            f"{BASE}/", json=new_account_payload(sample_identity.id)
        )
        assert response.status_code == 200

        stages = response.json()["stages"]
        assert {stage["stage_name"] for stage in stages} == COMMON_STAGE_NAMES
        assert all(stage["status"] == "pending" for stage in stages)
        assert all(stage["attempts"] == 0 for stage in stages)
        assert all(stage["completed_at"] is None for stage in stages)

    @pytest.mark.asyncio
    async def test_create_account_adds_site_specific_stages(
        self, authed_client: AsyncClient, sample_identity: Identity
    ):
        """A site with a known harder flow gets extra stages on top."""
        response = await authed_client.post(
            f"{BASE}/",
            json=new_account_payload(
                sample_identity.id,
                website_name="Google",
                website_url="https://accounts.google.com",
            ),
        )
        assert response.status_code == 200

        names = {stage["stage_name"] for stage in response.json()["stages"]}
        assert COMMON_STAGE_NAMES <= names
        assert "Phone Verification" in names
        assert "Two-Factor Auth" in names

    @pytest.mark.asyncio
    async def test_create_account_derives_domain_from_url(
        self,
        authed_client: AsyncClient,
        db_session: AsyncSession,
        sample_identity: Identity,
    ):
        """website_domain is derived from the URL when not supplied, `www.` stripped."""
        response = await authed_client.post(
            f"{BASE}/", json=new_account_payload(sample_identity.id)
        )
        assert response.status_code == 200

        stored = await db_session.get(Account, response.json()["id"])
        assert stored.website_domain == "example.com"

    @pytest.mark.asyncio
    async def test_create_account_keeps_explicit_domain(
        self,
        authed_client: AsyncClient,
        db_session: AsyncSession,
        sample_identity: Identity,
    ):
        """An explicit website_domain is not overwritten by the derivation."""
        response = await authed_client.post(
            f"{BASE}/",
            json=new_account_payload(
                sample_identity.id, website_domain="cdn.example.com"
            ),
        )
        assert response.status_code == 200

        stored = await db_session.get(Account, response.json()["id"])
        assert stored.website_domain == "cdn.example.com"

    @pytest.mark.asyncio
    async def test_create_account_requires_known_identity(
        self, authed_client: AsyncClient
    ):
        response = await authed_client.post(
            f"{BASE}/", json=new_account_payload(999999)
        )
        assert response.status_code == 404
        assert response.json()["detail"] == "Identity not found or not owned by user"

    @pytest.mark.asyncio
    async def test_create_account_rejects_another_users_identity(
        self, authed_client: AsyncClient, db_session: AsyncSession
    ):
        """You cannot hang an account off someone else's identity.

        This is the mass-assignment shape that matters here: identity_id comes
        from the body, so the route has to re-check ownership rather than trust
        it. A 404 (not 403) also avoids confirming the identity exists.
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

        foreign_identity = Identity(user_id=other_user.id, name="Not Yours")
        db_session.add(foreign_identity)
        await db_session.commit()
        await db_session.refresh(foreign_identity)

        response = await authed_client.post(
            f"{BASE}/", json=new_account_payload(foreign_identity.id)
        )
        assert response.status_code == 404

        # And nothing was written.
        result = await db_session.execute(select(Account))
        assert result.scalars().all() == []

    @pytest.mark.asyncio
    async def test_create_account_requires_website_name(
        self, authed_client: AsyncClient, sample_identity: Identity
    ):
        payload = new_account_payload(sample_identity.id)
        del payload["website_name"]
        response = await authed_client.post(f"{BASE}/", json=payload)
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_list_accounts_excludes_other_users(
        self, authed_client: AsyncClient, db_session: AsyncSession
    ):
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

        foreign_identity = Identity(user_id=other_user.id, name="Not Yours")
        db_session.add(foreign_identity)
        await db_session.commit()
        await db_session.refresh(foreign_identity)

        db_session.add(
            Account(
                identity_id=foreign_identity.id,
                website_name="Their Site",
                website_url="https://their-site.com",
            )
        )
        await db_session.commit()

        response = await authed_client.get(f"{BASE}/")
        assert response.status_code == 200
        assert response.json() == []


class TestAccountStages:
    """PATCH /{account_id}/stages/{stage_id}."""

    @pytest.mark.asyncio
    async def test_mark_stage_in_progress_sets_started_at(
        self,
        authed_client: AsyncClient,
        db_session: AsyncSession,
        sample_identity: Identity,
    ):
        created = await authed_client.post(
            f"{BASE}/", json=new_account_payload(sample_identity.id)
        )
        account_id = created.json()["id"]
        stage = (
            (
                await db_session.execute(
                    select(AccountStage).where(AccountStage.account_id == account_id)
                )
            )
            .scalars()
            .first()
        )

        response = await authed_client.patch(
            f"{BASE}/{account_id}/stages/{stage.id}", json={"status": "in_progress"}
        )
        assert response.status_code == 200
        assert response.json() == {"message": "Stage updated successfully"}

        await db_session.refresh(stage)
        assert stage.status is StageStatus.IN_PROGRESS
        assert stage.started_at is not None
        assert stage.completed_at is None
        assert stage.attempts == 1

    @pytest.mark.asyncio
    async def test_mark_stage_completed_sets_completed_at(
        self,
        authed_client: AsyncClient,
        db_session: AsyncSession,
        sample_identity: Identity,
    ):
        created = await authed_client.post(
            f"{BASE}/", json=new_account_payload(sample_identity.id)
        )
        account_id = created.json()["id"]
        stage = (
            (
                await db_session.execute(
                    select(AccountStage).where(AccountStage.account_id == account_id)
                )
            )
            .scalars()
            .first()
        )

        response = await authed_client.patch(
            f"{BASE}/{account_id}/stages/{stage.id}", json={"status": "completed"}
        )
        assert response.status_code == 200

        await db_session.refresh(stage)
        assert stage.status is StageStatus.COMPLETED
        assert stage.completed_at is not None

    @pytest.mark.asyncio
    async def test_stage_data_is_stored_encrypted(
        self,
        authed_client: AsyncClient,
        db_session: AsyncSession,
        sample_identity: Identity,
    ):
        """stage_data can carry secrets, so it must not land in the clear."""
        created = await authed_client.post(
            f"{BASE}/", json=new_account_payload(sample_identity.id)
        )
        account_id = created.json()["id"]
        stage = (
            (
                await db_session.execute(
                    select(AccountStage).where(AccountStage.account_id == account_id)
                )
            )
            .scalars()
            .first()
        )

        response = await authed_client.patch(
            f"{BASE}/{account_id}/stages/{stage.id}",
            json={
                "status": "failed",
                "error_message": "captcha timed out",
                "stage_data": {"otp": "123456"},
            },
        )
        assert response.status_code == 200

        await db_session.refresh(stage)
        assert stage.encrypted_stage_data is not None
        assert "123456" not in stage.encrypted_stage_data
        # error_message is operator-facing text, stored as given.
        assert stage.error_message == "captcha timed out"

    @pytest.mark.asyncio
    async def test_update_unknown_stage_is_404(
        self, authed_client: AsyncClient, sample_identity: Identity
    ):
        created = await authed_client.post(
            f"{BASE}/", json=new_account_payload(sample_identity.id)
        )
        account_id = created.json()["id"]

        response = await authed_client.patch(
            f"{BASE}/{account_id}/stages/999999", json={"status": "completed"}
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_stage_must_belong_to_the_named_account(
        self,
        authed_client: AsyncClient,
        db_session: AsyncSession,
        sample_identity: Identity,
    ):
        """A stage id is only valid under its own account.

        The route filters on account_id as well as stage id; without that,
        knowing any stage id would be enough to mutate it through an unrelated
        account in the path.
        """
        first = await authed_client.post(
            f"{BASE}/", json=new_account_payload(sample_identity.id)
        )
        second = await authed_client.post(
            f"{BASE}/",
            json=new_account_payload(
                sample_identity.id,
                website_name="Other",
                website_url="https://other.com",
            ),
        )

        stage_of_first = (
            (
                await db_session.execute(
                    select(AccountStage).where(
                        AccountStage.account_id == first.json()["id"]
                    )
                )
            )
            .scalars()
            .first()
        )

        response = await authed_client.patch(
            f"{BASE}/{second.json()['id']}/stages/{stage_of_first.id}",
            json={"status": "completed"},
        )
        assert response.status_code == 404


class TestAccountsRouting:
    """The prefix itself, which is what #80 turned out to be about."""

    @pytest.mark.asyncio
    async def test_unversioned_path_is_not_served(self, authed_client: AsyncClient):
        """`/api/accounts` must not exist.

        The frontend used to call exactly this and got a 404 in production.
        Asserting the absence keeps a compatibility alias from quietly
        reintroducing an un-versioned surface that gate-api-version forbids.
        """
        response = await authed_client.get("/api/accounts")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_requires_authentication(self, client: AsyncClient):
        response = await client.get(f"{BASE}/")
        assert response.status_code in (401, 403)


class TestAccountsRouterRegistration:
    """Guards against the duplicate-route regression this file was written with.

    `app/routers/accounts.py` had shipped with its entire route section pasted
    twice -- `GET /`, `POST /` and `PATCH /{account_id}/stages/{stage_id}` were
    each registered two times. FastAPI matches in declaration order, so the
    second copy was dead code, but it doubled the OpenAPI entries and left two
    bodies that would silently diverge the moment anyone edited one of them.
    """

    @pytest.mark.asyncio
    async def test_each_route_is_registered_once(self):
        from collections import Counter

        from app.routers.accounts import router

        seen = Counter()
        for route in router.routes:
            for method in sorted(route.methods):
                seen[(method, route.path)] += 1

        duplicated = {key: count for key, count in seen.items() if count > 1}
        assert not duplicated, f"route registered more than once: {duplicated}"

    @pytest.mark.asyncio
    async def test_expected_routes_are_present(self):
        from app.routers.accounts import router

        registered = {
            (method, route.path) for route in router.routes for method in route.methods
        }
        assert ("GET", "/") in registered
        assert ("POST", "/") in registered
        assert ("PATCH", "/{account_id}/stages/{stage_id}") in registered
