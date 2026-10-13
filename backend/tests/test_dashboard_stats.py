"""Tests for GET /api/v1/dashboard/stats.

Covers the empty case, ownership scoping of the identity, account and automation
job figures, and the success-rate arithmetic (cancelled and in-flight jobs are
excluded from both sides of the ratio).
"""

from datetime import datetime

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.account import Account
from app.models.identity import Identity
from app.models.user import User
from app.services.background_service import AutomationJob
from app.utils.encryption import encrypt_field

BASE = "/api/v1/dashboard/stats"


class _FakeManager:
    def __init__(self, jobs):
        self.automation_jobs = {job.job_id: job for job in jobs}


def _job(job_id: str, identity_id: int, status: str) -> AutomationJob:
    return AutomationJob(
        job_id=job_id,
        website="example.com",
        identity_id=identity_id,
        email_account="unused@example.com",
        signup_data={},
        status=status,
        created_at=datetime(2026, 1, 1),
    )


def _use_jobs(monkeypatch, jobs):
    manager = _FakeManager(jobs)

    async def fake_get_background_manager():
        return manager

    monkeypatch.setattr(
        "app.routers.dashboard.get_background_manager", fake_get_background_manager
    )


@pytest.mark.asyncio
async def test_stats_are_zero_without_data(authed_client: AsyncClient, monkeypatch):
    """No identities, accounts or jobs (and no started manager) report zeros."""
    monkeypatch.setattr(
        "app.routers.dashboard.get_background_manager",
        _raise_not_initialized,
    )

    response = await authed_client.get(BASE)

    assert response.status_code == 200
    assert response.json() == {"identities": 0, "accounts": 0, "successRate": 0.0}


async def _raise_not_initialized():
    raise RuntimeError("Background service manager not initialized")


@pytest.mark.asyncio
async def test_counts_only_include_the_current_user(
    authed_client: AsyncClient,
    db_session: AsyncSession,
    sample_identity: Identity,
    sample_account: Account,
    monkeypatch,
):
    """Another user's identity and account are not counted."""
    other_user = User(
        username="otheruser",
        email="otheruser@example.com",
        hashed_password="not-a-real-hash",
        master_key_hash="not-a-real-master-key-hash",
        is_active=True,
    )
    db_session.add(other_user)
    await db_session.commit()
    await db_session.refresh(other_user)

    other_identity = Identity(
        user_id=other_user.id,
        name="Other Identity",
        encrypted_first_name=encrypt_field("Other"),
        encrypted_last_name=encrypt_field("Person"),
        encrypted_email=encrypt_field("other@example.com"),
    )
    db_session.add(other_identity)
    await db_session.commit()
    await db_session.refresh(other_identity)

    db_session.add(
        Account(
            identity_id=other_identity.id,
            website_name="Other Site",
            website_url="https://other-site.com",
            website_domain="other-site.com",
            encrypted_username=encrypt_field("otheruser"),
            encrypted_email=encrypt_field("other@example.com"),
            account_type="free",
            signup_method="manual",
            is_active=True,
            signup_completed=False,
        )
    )
    await db_session.commit()

    _use_jobs(monkeypatch, [])

    response = await authed_client.get(BASE)

    assert response.status_code == 200
    assert response.json() == {"identities": 1, "accounts": 1, "successRate": 0.0}


@pytest.mark.asyncio
async def test_success_rate_counts_completed_over_finished_jobs(
    authed_client: AsyncClient,
    sample_identity: Identity,
    monkeypatch,
):
    """successRate = completed / (completed + failed); other statuses are ignored."""
    own = sample_identity.id
    jobs = [
        _job("job_completed_1", own, "completed"),
        _job("job_completed_2", own, "completed"),
        _job("job_completed_3", own, "completed"),
        _job("job_failed_1", own, "failed"),
        _job("job_pending", own, "pending"),
        _job("job_running", own, "running"),
        _job("job_verification", own, "awaiting_verification"),
        _job("job_cancelled", own, "cancelled"),
        # Jobs for another identity must not move this user's rate.
        _job("job_foreign_failed", own + 1000, "failed"),
        _job("job_foreign_completed", own + 1000, "completed"),
    ]
    _use_jobs(monkeypatch, jobs)

    response = await authed_client.get(BASE)

    assert response.status_code == 200
    assert response.json() == {"identities": 1, "accounts": 0, "successRate": 75.0}


@pytest.mark.asyncio
async def test_success_rate_is_zero_when_no_job_finished(
    authed_client: AsyncClient,
    sample_identity: Identity,
    monkeypatch,
):
    """Only in-flight jobs means no finished runs, so the rate is 0 and not NaN."""
    _use_jobs(monkeypatch, [_job("job_pending", sample_identity.id, "pending")])

    response = await authed_client.get(BASE)

    assert response.status_code == 200
    assert response.json()["successRate"] == 0.0
