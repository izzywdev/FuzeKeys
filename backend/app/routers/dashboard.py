import logging

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.database import get_db
from app.models.account import Account
from app.models.identity import Identity
from app.models.user import User
from app.routers.auth import get_current_user
from app.services.background_service import AutomationJob, get_background_manager

logger = logging.getLogger(__name__)

router = APIRouter()

# Job outcomes that count toward the success rate. `cancelled`, `pending`,
# `running` and `awaiting_verification` are not outcomes yet (or were not runs
# that succeeded or failed), so they are excluded from both sides of the ratio.
_SUCCESS_STATUS = "completed"
_FAILURE_STATUS = "failed"


class DashboardStats(BaseModel):
    identities: int = Field(..., description="Identities owned by the current user")
    accounts: int = Field(
        ..., description="Accounts under the current user's identities"
    )
    successRate: float = Field(
        ...,
        ge=0,
        le=100,
        description=(
            "Percent (0-100) of the current user's finished automation jobs that "
            "completed, out of jobs that completed or failed. 0 when there are none. "
            "Window: every job the background manager currently retains (no time "
            "window). Each job counts once by its final status, so a job that failed "
            "and was later retried to completion counts as completed."
        ),
    )


async def _user_automation_jobs(user_identity_ids: set[int]) -> list[AutomationJob]:
    """Automation jobs whose identity belongs to the current user.

    The job store is in-process and not keyed by owner, so ownership is derived
    from the job's identity_id. If the background manager was never started
    there are no jobs to report, which is an empty result, not an error.
    """
    try:
        manager = await get_background_manager()
    except RuntimeError:
        return []
    return [
        job
        for job in manager.automation_jobs.values()
        if job.identity_id in user_identity_ids
    ]


@router.get(
    "/stats",
    response_model=DashboardStats,
    summary="Dashboard statistics",
    description=(
        "Counts of the current user's identities and accounts, and the automation "
        "success rate. See DashboardStats.successRate for the exact window and "
        "semantics."
    ),
    # A single aggregate object, not a collection (matches sites /stats/overview).
    openapi_extra={"x-pagination": "exempt"},
)
async def get_dashboard_stats(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return identity, account and automation success-rate figures for the current user."""
    try:
        identity_ids = set(
            (
                await db.execute(
                    select(Identity.id).where(Identity.user_id == current_user.id)
                )
            )
            .scalars()
            .all()
        )
        # Same filters as the `total` of GET /identities/ and GET /accounts/.
        identities = len(identity_ids)
        accounts = (
            await db.execute(
                select(func.count(Account.id))
                .join(Identity)
                .where(Identity.user_id == current_user.id)
            )
        ).scalar_one()

        jobs = await _user_automation_jobs(identity_ids)
        succeeded = sum(1 for job in jobs if job.status == _SUCCESS_STATUS)
        failed = sum(1 for job in jobs if job.status == _FAILURE_STATUS)
        finished = succeeded + failed
        success_rate = round(succeeded * 100 / finished, 1) if finished else 0.0

        return DashboardStats(
            identities=identities,
            accounts=accounts,
            successRate=success_rate,
        )

    except HTTPException:
        raise
    except Exception:
        # Never log record contents here: they can carry PII.
        logger.error("Error computing dashboard stats for user_id=%s", current_user.id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error retrieving dashboard stats",
        )
