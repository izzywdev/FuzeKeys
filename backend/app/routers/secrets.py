"""Secret versioning & environment-grouped rollback API (/api/v1/secrets).

Groups secrets into environments (Dev/Prod/...), keeps an immutable version
history for every secret, and supports rolling back a single secret — or a whole
environment — to a prior value.

Security: list/metadata endpoints NEVER return a decrypted value. Values are
returned only by the explicit, audited ``/reveal`` and ``/export`` endpoints.
All operations are scoped to the authenticated user; encryption fails closed
(HTTP 503) when ``CREDENTIAL_ENCRYPTION_KEY`` is missing/invalid.
"""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query, Response, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User
from app.routers.auth import get_current_user
from app.services import secret_versioning as svc
from app.utils.pagination import Page, PageInfo

router = APIRouter()

_KEY_PATTERN = r"^[A-Za-z_][A-Za-z0-9_]*$"
_NAME_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9 _-]*$"


# --- schemas --------------------------------------------------------------


class EnvironmentCreate(BaseModel):
    model_config = {"extra": "forbid"}
    name: str = Field(min_length=1, max_length=100, pattern=_NAME_PATTERN)
    description: Optional[str] = Field(default=None, max_length=500)


class EnvironmentResponse(BaseModel):
    id: int
    name: str
    description: Optional[str]
    current_snapshot_version: int
    snapshot_count: int
    secret_count: int
    created_at: Optional[datetime]
    updated_at: Optional[datetime]


class SecretCreate(BaseModel):
    model_config = {"extra": "forbid"}
    key: str = Field(min_length=1, max_length=255, pattern=_KEY_PATTERN)
    value: str = Field(min_length=1, max_length=65536)
    description: Optional[str] = Field(default=None, max_length=500)
    comment: Optional[str] = Field(default=None, max_length=500)


class SecretUpdate(BaseModel):
    model_config = {"extra": "forbid"}
    value: str = Field(min_length=1, max_length=65536)
    comment: Optional[str] = Field(default=None, max_length=500)


class SecretResponse(BaseModel):
    id: int
    environment_id: int
    key: str
    description: Optional[str]
    current_version: int
    is_deleted: bool
    created_at: Optional[datetime]
    updated_at: Optional[datetime]


class VersionResponse(BaseModel):
    """Version metadata — never includes the decrypted value."""

    version: int
    change_comment: Optional[str]
    is_rollback: bool
    rolled_back_from_version: Optional[int]
    created_at: Optional[datetime]
    created_by_user_id: Optional[int]


class RevealResponse(BaseModel):
    secret_id: int
    version: int
    value: str


class RevealRequest(BaseModel):
    model_config = {"extra": "forbid"}
    version: Optional[int] = Field(default=None, ge=1)


class RollbackSecretRequest(BaseModel):
    model_config = {"extra": "forbid"}
    version: int = Field(ge=1)


class SnapshotResponse(BaseModel):
    snapshot_version: int
    label: Optional[str]
    is_rollback: bool
    rolled_back_from_snapshot: Optional[int]
    created_at: Optional[datetime]


class RollbackEnvRequest(BaseModel):
    model_config = {"extra": "forbid"}
    snapshot_version: int = Field(ge=1)


class ExportResponse(BaseModel):
    environment_id: int
    snapshot_version: Optional[int]
    values: dict[str, str]


# --- helpers --------------------------------------------------------------


def _page(items: list, offset: int, limit: int, total: int) -> PageInfo:
    return PageInfo(
        offset=offset,
        limit=limit,
        total=total,
        next_offset=offset + limit if offset + limit < total else None,
    )


async def _env_response(db: AsyncSession, env) -> EnvironmentResponse:
    secret_count = await svc.count_active_secrets(db, env.id)
    return EnvironmentResponse(
        id=env.id,
        name=env.name,
        description=env.description,
        current_snapshot_version=env.current_snapshot_version,
        snapshot_count=env.current_snapshot_version,
        secret_count=secret_count,
        created_at=env.created_at,
        updated_at=env.updated_at,
    )


def _secret_response(secret) -> SecretResponse:
    return SecretResponse(
        id=secret.id,
        environment_id=secret.environment_id,
        key=secret.key,
        description=secret.description,
        current_version=secret.current_version,
        is_deleted=secret.is_deleted,
        created_at=secret.created_at,
        updated_at=secret.updated_at,
    )


# --- environments ---------------------------------------------------------


@router.post("/environments", response_model=EnvironmentResponse, status_code=201)
async def create_environment(
    body: EnvironmentCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    env = await svc.create_environment(db, current_user.id, body.name, body.description)
    return await _env_response(db, env)


@router.get("/environments", response_model=Page[EnvironmentResponse])
async def list_environments(
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    envs, total = await svc.list_environments(db, current_user.id, offset, limit)
    items = [await _env_response(db, e) for e in envs]
    return Page(items=items, page=_page(items, offset, limit, total))


@router.get("/environments/{env_id}", response_model=EnvironmentResponse)
async def get_environment(
    env_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    env = await svc.get_environment(db, current_user.id, env_id)
    return await _env_response(db, env)


@router.delete("/environments/{env_id}", status_code=204)
async def delete_environment(
    env_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await svc.delete_environment(db, current_user.id, env_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/environments/{env_id}/snapshots", response_model=Page[SnapshotResponse])
async def list_snapshots(
    env_id: int,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    snaps, total = await svc.list_snapshots(db, current_user.id, env_id, offset, limit)
    items = [
        SnapshotResponse(
            snapshot_version=s.snapshot_version,
            label=s.label,
            is_rollback=s.is_rollback,
            rolled_back_from_snapshot=s.rolled_back_from_snapshot,
            created_at=s.created_at,
        )
        for s in snaps
    ]
    return Page(items=items, page=_page(items, offset, limit, total))


@router.post("/environments/{env_id}/rollback", response_model=EnvironmentResponse)
async def rollback_environment(
    env_id: int,
    body: RollbackEnvRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    env = await svc.rollback_environment(
        db, current_user.id, env_id, body.snapshot_version
    )
    return await _env_response(db, env)


@router.get(
    "/environments/{env_id}/export",
    response_model=ExportResponse,
    openapi_extra={"x-pagination": "exempt"},  # bounded by env secrets count, not a paginated list
)
async def export_environment(
    env_id: int,
    snapshot: Optional[int] = Query(default=None, ge=1),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    values = await svc.export_environment(db, current_user.id, env_id, snapshot)
    return ExportResponse(
        environment_id=env_id, snapshot_version=snapshot, values=values
    )


# --- secrets --------------------------------------------------------------


@router.post(
    "/environments/{env_id}/secrets", response_model=SecretResponse, status_code=201
)
async def create_secret(
    env_id: int,
    body: SecretCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    secret = await svc.create_secret(
        db,
        current_user.id,
        env_id,
        body.key,
        body.value,
        body.description,
        body.comment,
    )
    return _secret_response(secret)


@router.get("/environments/{env_id}/secrets", response_model=Page[SecretResponse])
async def list_secrets(
    env_id: int,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    secrets, total = await svc.list_secrets(db, current_user.id, env_id, offset, limit)
    items = [_secret_response(s) for s in secrets]
    return Page(items=items, page=_page(items, offset, limit, total))


@router.put("/environments/{env_id}/secrets/{secret_id}", response_model=SecretResponse)
async def update_secret(
    env_id: int,
    secret_id: int,
    body: SecretUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    secret = await svc.update_secret(
        db, current_user.id, env_id, secret_id, body.value, body.comment
    )
    return _secret_response(secret)


@router.delete("/environments/{env_id}/secrets/{secret_id}", status_code=204)
async def delete_secret(
    env_id: int,
    secret_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await svc.delete_secret(db, current_user.id, env_id, secret_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/environments/{env_id}/secrets/{secret_id}/versions",
    response_model=Page[VersionResponse],
)
async def list_versions(
    env_id: int,
    secret_id: int,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    versions, total = await svc.list_versions(
        db, current_user.id, env_id, secret_id, offset, limit
    )
    items = [
        VersionResponse(
            version=v.version,
            change_comment=v.change_comment,
            is_rollback=v.is_rollback,
            rolled_back_from_version=v.rolled_back_from_version,
            created_at=v.created_at,
            created_by_user_id=v.created_by_user_id,
        )
        for v in versions
    ]
    return Page(items=items, page=_page(items, offset, limit, total))


@router.post(
    "/environments/{env_id}/secrets/{secret_id}/reveal", response_model=RevealResponse
)
async def reveal_secret(
    env_id: int,
    secret_id: int,
    body: RevealRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    version, value = await svc.reveal_value(
        db, current_user.id, env_id, secret_id, body.version
    )
    return RevealResponse(secret_id=secret_id, version=version, value=value)


@router.post(
    "/environments/{env_id}/secrets/{secret_id}/rollback",
    response_model=SecretResponse,
)
async def rollback_secret(
    env_id: int,
    secret_id: int,
    body: RollbackSecretRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    secret = await svc.rollback_secret(
        db, current_user.id, env_id, secret_id, body.version
    )
    return _secret_response(secret)
