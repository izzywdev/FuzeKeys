"""Service layer for secret versioning and environment-grouped rollback.

Design / security invariants
----------------------------
* Values are encrypted with the SAME Fernet ``CREDENTIAL_ENCRYPTION_KEY`` regime
  as the credentials API. We reuse ``app.routers.credentials._get_cipher`` so the
  key handling and fail-closed (HTTP 503) behaviour are identical and there is a
  single source of truth for the key.
* Nothing here ever stores, logs, or returns plaintext except the two explicit,
  audited reveal/export paths. Version/snapshot rows carry ciphertext (or a
  reference to a ciphertext row) only.
* Rollback is append-only at both levels — existing version/snapshot rows are
  never mutated or deleted. A rollback copies an old ciphertext into a NEW
  current version (same key, so no re-encryption is needed).
* Every query is scoped to the authenticated ``user_id`` (SQL ownership). The
  platform ``require_owner_permission`` helper only covers Identity/Account, so
  these user-owned resources rely on strict ``user_id`` filtering.
"""

import hashlib
import hmac
import logging
import os
from typing import Optional

from cryptography.fernet import Fernet
from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.secret import (
    EnvironmentSnapshot,
    Secret,
    SecretEnvironment,
    SecretSnapshotEntry,
    SecretVersion,
)
from app.utils.logging import log_security_event

logger = logging.getLogger(__name__)


# --- crypto helpers -------------------------------------------------------
# SECURITY: identical fail-closed Fernet regime as app.routers.credentials
# (same CREDENTIAL_ENCRYPTION_KEY env var). Self-contained here so the service
# layer does not import a router. If the key is missing/blank or not a valid
# Fernet key, every crypto path raises HTTP 503 — no ephemeral/fallback key is
# ever fabricated, so no endpoint can operate with an insecure or absent key.


def _get_cipher() -> Fernet:
    key = os.getenv("CREDENTIAL_ENCRYPTION_KEY")
    if not key or not key.strip():
        logger.error(
            "Refusing secret crypto operation: CREDENTIAL_ENCRYPTION_KEY unset/blank."
        )
        log_security_event(
            "secret_crypto_unavailable", details={"reason": "encryption_key_missing"}
        )
        raise HTTPException(
            status_code=503, detail="Secret encryption is not configured"
        )
    try:
        return Fernet(key.strip().encode())
    except Exception as exc:  # noqa: BLE001 - malformed key value
        # Static message with no interpolation — the exception is deliberately
        # NOT logged, since a malformed-key error can echo key material. The
        # reason is recorded via log_security_event below.
        # nosemgrep: python.lang.security.audit.logging.logger-credential-leak.python-logger-credential-disclosure
        logger.error("Refusing secret crypto operation: invalid Fernet key")
        log_security_event(
            "secret_crypto_unavailable", details={"reason": "encryption_key_invalid"}
        )
        raise HTTPException(
            status_code=503, detail="Secret encryption is not configured"
        )


def _encrypt(plaintext: str) -> str:
    """Encrypt a value. Fails closed (HTTP 503) if the key is unavailable."""
    return _get_cipher().encrypt(plaintext.encode()).decode()


def _decrypt(ciphertext: str) -> str:
    """Decrypt a stored ciphertext. Fails closed (HTTP 503) if unavailable."""
    return _get_cipher().decrypt(ciphertext.encode()).decode()


def _value_hmac(plaintext: str) -> Optional[str]:
    """Keyed HMAC of the plaintext for no-op change detection.

    Keyed with CREDENTIAL_ENCRYPTION_KEY so the digest is not a bare hash of a
    possibly low-entropy secret. Returns None when no key is configured (the
    encrypt path will already have failed closed before this matters).
    """
    key = os.getenv("CREDENTIAL_ENCRYPTION_KEY")
    if not key or not key.strip():
        return None
    return hmac.new(
        key.strip().encode(), plaintext.encode(), hashlib.sha256
    ).hexdigest()


# --- ownership lookups ----------------------------------------------------


async def _get_owned_environment(
    db: AsyncSession, user_id: int, env_id: int
) -> SecretEnvironment:
    result = await db.execute(
        select(SecretEnvironment).where(
            SecretEnvironment.id == env_id,
            SecretEnvironment.user_id == user_id,
        )
    )
    env = result.scalar_one_or_none()
    if env is None:
        raise HTTPException(status_code=404, detail="Environment not found")
    return env


async def _get_owned_secret(
    db: AsyncSession, user_id: int, env_id: int, secret_id: int
) -> Secret:
    result = await db.execute(
        select(Secret)
        .join(SecretEnvironment, Secret.environment_id == SecretEnvironment.id)
        .where(
            Secret.id == secret_id,
            Secret.environment_id == env_id,
            SecretEnvironment.user_id == user_id,
        )
    )
    secret = result.scalar_one_or_none()
    if secret is None:
        raise HTTPException(status_code=404, detail="Secret not found")
    return secret


async def _get_version_row(
    db: AsyncSession, secret_id: int, version: int
) -> Optional[SecretVersion]:
    result = await db.execute(
        select(SecretVersion).where(
            SecretVersion.secret_id == secret_id,
            SecretVersion.version == version,
        )
    )
    return result.scalar_one_or_none()


async def count_active_secrets(db: AsyncSession, env_id: int) -> int:
    result = await db.execute(
        select(func.count(Secret.id)).where(
            Secret.environment_id == env_id,
            Secret.is_deleted.is_(False),
        )
    )
    return int(result.scalar_one())


# --- version / snapshot writers (append-only) -----------------------------


async def _append_version_from_plaintext(
    db: AsyncSession,
    secret: Secret,
    plaintext: str,
    comment: Optional[str],
    user_id: int,
    *,
    is_rollback: bool = False,
    rolled_back_from: Optional[int] = None,
) -> SecretVersion:
    new_version = secret.current_version + 1
    row = SecretVersion(
        secret_id=secret.id,
        version=new_version,
        encrypted_value=_encrypt(plaintext),
        value_hmac=_value_hmac(plaintext),
        change_comment=comment,
        is_rollback=is_rollback,
        rolled_back_from_version=rolled_back_from,
        created_by_user_id=user_id,
    )
    db.add(row)
    secret.current_version = new_version
    secret.is_deleted = False
    await db.flush()
    return row


async def _append_version_from_ciphertext(
    db: AsyncSession,
    secret: Secret,
    ciphertext: str,
    value_hmac: Optional[str],
    comment: Optional[str],
    user_id: int,
    *,
    is_rollback: bool,
    rolled_back_from: Optional[int],
) -> SecretVersion:
    new_version = secret.current_version + 1
    row = SecretVersion(
        secret_id=secret.id,
        version=new_version,
        encrypted_value=ciphertext,
        value_hmac=value_hmac,
        change_comment=comment,
        is_rollback=is_rollback,
        rolled_back_from_version=rolled_back_from,
        created_by_user_id=user_id,
    )
    db.add(row)
    secret.current_version = new_version
    secret.is_deleted = False
    await db.flush()
    return row


async def _record_snapshot(
    db: AsyncSession,
    env: SecretEnvironment,
    label: Optional[str],
    user_id: int,
    *,
    is_rollback: bool = False,
    rolled_back_from: Optional[int] = None,
) -> EnvironmentSnapshot:
    """Record an immutable snapshot pinning each active secret to its version."""
    new_v = env.current_snapshot_version + 1
    snapshot = EnvironmentSnapshot(
        environment_id=env.id,
        snapshot_version=new_v,
        label=label,
        is_rollback=is_rollback,
        rolled_back_from_snapshot=rolled_back_from,
        created_by_user_id=user_id,
    )
    db.add(snapshot)
    await db.flush()

    # Pin every active secret (current_version > 0, not soft-deleted).
    result = await db.execute(
        select(Secret).where(
            Secret.environment_id == env.id,
            Secret.is_deleted.is_(False),
            Secret.current_version > 0,
        )
    )
    for secret in result.scalars().all():
        version_row = await _get_version_row(db, secret.id, secret.current_version)
        if version_row is None:
            continue
        db.add(
            SecretSnapshotEntry(
                snapshot_id=snapshot.id,
                secret_id=secret.id,
                secret_version_id=version_row.id,
                secret_key=secret.key,
                version=secret.current_version,
            )
        )
    env.current_snapshot_version = new_v
    await db.flush()
    return snapshot


# --- environments ---------------------------------------------------------


async def create_environment(
    db: AsyncSession, user_id: int, name: str, description: Optional[str]
) -> SecretEnvironment:
    existing = await db.execute(
        select(SecretEnvironment).where(
            SecretEnvironment.user_id == user_id,
            SecretEnvironment.name == name,
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=409, detail=f"Environment '{name}' already exists"
        )
    env = SecretEnvironment(user_id=user_id, name=name, description=description)
    db.add(env)
    await db.commit()
    await db.refresh(env)
    return env


async def list_environments(
    db: AsyncSession, user_id: int, offset: int, limit: int
) -> tuple[list[SecretEnvironment], int]:
    total_result = await db.execute(
        select(func.count(SecretEnvironment.id)).where(
            SecretEnvironment.user_id == user_id
        )
    )
    total = int(total_result.scalar_one())
    result = await db.execute(
        select(SecretEnvironment)
        .where(SecretEnvironment.user_id == user_id)
        .order_by(SecretEnvironment.name)
        .offset(offset)
        .limit(limit)
    )
    return list(result.scalars().all()), total


async def get_environment(
    db: AsyncSession, user_id: int, env_id: int
) -> SecretEnvironment:
    return await _get_owned_environment(db, user_id, env_id)


async def delete_environment(db: AsyncSession, user_id: int, env_id: int) -> None:
    env = await _get_owned_environment(db, user_id, env_id)
    await db.delete(env)
    await db.commit()


# --- secrets --------------------------------------------------------------


async def create_secret(
    db: AsyncSession,
    user_id: int,
    env_id: int,
    key: str,
    value: str,
    description: Optional[str],
    comment: Optional[str],
) -> Secret:
    env = await _get_owned_environment(db, user_id, env_id)
    existing = await db.execute(
        select(Secret).where(Secret.environment_id == env_id, Secret.key == key)
    )
    secret = existing.scalar_one_or_none()
    if secret is not None and not secret.is_deleted:
        raise HTTPException(
            status_code=409, detail=f"Secret '{key}' already exists in environment"
        )
    if secret is None:
        secret = Secret(environment_id=env_id, key=key, description=description)
        db.add(secret)
        await db.flush()
    else:
        # Re-create a previously soft-deleted key (keeps the unique row).
        secret.description = description
    await _append_version_from_plaintext(
        db, secret, value, comment or "Created", user_id
    )
    await _record_snapshot(db, env, f"Set {key}", user_id)
    await db.commit()
    await db.refresh(secret)
    return secret


async def update_secret(
    db: AsyncSession,
    user_id: int,
    env_id: int,
    secret_id: int,
    value: str,
    comment: Optional[str],
) -> Secret:
    env = await _get_owned_environment(db, user_id, env_id)
    secret = await _get_owned_secret(db, user_id, env_id, secret_id)
    # No-op if the value is unchanged (keeps history free of duplicate versions).
    new_hmac = _value_hmac(value)
    current = await _get_version_row(db, secret.id, secret.current_version)
    if current is not None and new_hmac is not None and current.value_hmac == new_hmac:
        return secret
    await _append_version_from_plaintext(
        db, secret, value, comment or "Updated", user_id
    )
    await _record_snapshot(db, env, f"Update {secret.key}", user_id)
    await db.commit()
    await db.refresh(secret)
    return secret


async def list_secrets(
    db: AsyncSession, user_id: int, env_id: int, offset: int, limit: int
) -> tuple[list[Secret], int]:
    await _get_owned_environment(db, user_id, env_id)
    total_result = await db.execute(
        select(func.count(Secret.id)).where(
            Secret.environment_id == env_id, Secret.is_deleted.is_(False)
        )
    )
    total = int(total_result.scalar_one())
    result = await db.execute(
        select(Secret)
        .where(Secret.environment_id == env_id, Secret.is_deleted.is_(False))
        .order_by(Secret.key)
        .offset(offset)
        .limit(limit)
    )
    return list(result.scalars().all()), total


async def delete_secret(
    db: AsyncSession, user_id: int, env_id: int, secret_id: int
) -> None:
    env = await _get_owned_environment(db, user_id, env_id)
    secret = await _get_owned_secret(db, user_id, env_id, secret_id)
    secret.is_deleted = True
    await db.flush()
    await _record_snapshot(db, env, f"Delete {secret.key}", user_id)
    await db.commit()


async def list_versions(
    db: AsyncSession, user_id: int, env_id: int, secret_id: int, offset: int, limit: int
) -> tuple[list[SecretVersion], int]:
    await _get_owned_secret(db, user_id, env_id, secret_id)
    total_result = await db.execute(
        select(func.count(SecretVersion.id)).where(SecretVersion.secret_id == secret_id)
    )
    total = int(total_result.scalar_one())
    result = await db.execute(
        select(SecretVersion)
        .where(SecretVersion.secret_id == secret_id)
        .order_by(SecretVersion.version.desc())
        .offset(offset)
        .limit(limit)
    )
    return list(result.scalars().all()), total


async def reveal_value(
    db: AsyncSession,
    user_id: int,
    env_id: int,
    secret_id: int,
    version: Optional[int],
) -> tuple[int, str]:
    """Return (version, plaintext) for a secret. Audited."""
    secret = await _get_owned_secret(db, user_id, env_id, secret_id)
    target = version if version is not None else secret.current_version
    if target < 1:
        raise HTTPException(status_code=404, detail="No version to reveal")
    row = await _get_version_row(db, secret.id, target)
    if row is None:
        raise HTTPException(status_code=404, detail=f"Version {target} not found")
    log_security_event(
        "secret_value_revealed",
        user_id=user_id,
        details={"environment_id": env_id, "secret_id": secret_id, "version": target},
    )
    return target, _decrypt(row.encrypted_value)


async def rollback_secret(
    db: AsyncSession,
    user_id: int,
    env_id: int,
    secret_id: int,
    target_version: int,
) -> Secret:
    env = await _get_owned_environment(db, user_id, env_id)
    secret = await _get_owned_secret(db, user_id, env_id, secret_id)
    target = await _get_version_row(db, secret.id, target_version)
    if target is None:
        raise HTTPException(
            status_code=404, detail=f"Version {target_version} not found"
        )
    await _append_version_from_ciphertext(
        db,
        secret,
        target.encrypted_value,
        target.value_hmac,
        f"Rollback to v{target_version}",
        user_id,
        is_rollback=True,
        rolled_back_from=target_version,
    )
    await _record_snapshot(
        db, env, f"Rollback {secret.key} to v{target_version}", user_id
    )
    await db.commit()
    await db.refresh(secret)
    log_security_event(
        "secret_rolled_back",
        user_id=user_id,
        details={
            "environment_id": env_id,
            "secret_id": secret_id,
            "to_version": target_version,
        },
    )
    return secret


# --- snapshots & environment rollback ------------------------------------


async def list_snapshots(
    db: AsyncSession, user_id: int, env_id: int, offset: int, limit: int
) -> tuple[list[EnvironmentSnapshot], int]:
    await _get_owned_environment(db, user_id, env_id)
    total_result = await db.execute(
        select(func.count(EnvironmentSnapshot.id)).where(
            EnvironmentSnapshot.environment_id == env_id
        )
    )
    total = int(total_result.scalar_one())
    result = await db.execute(
        select(EnvironmentSnapshot)
        .where(EnvironmentSnapshot.environment_id == env_id)
        .order_by(EnvironmentSnapshot.snapshot_version.desc())
        .offset(offset)
        .limit(limit)
    )
    return list(result.scalars().all()), total


async def _get_snapshot(
    db: AsyncSession, env_id: int, snapshot_version: int
) -> EnvironmentSnapshot:
    result = await db.execute(
        select(EnvironmentSnapshot).where(
            EnvironmentSnapshot.environment_id == env_id,
            EnvironmentSnapshot.snapshot_version == snapshot_version,
        )
    )
    snapshot = result.scalar_one_or_none()
    if snapshot is None:
        raise HTTPException(
            status_code=404, detail=f"Snapshot v{snapshot_version} not found"
        )
    return snapshot


async def rollback_environment(
    db: AsyncSession, user_id: int, env_id: int, target_snapshot_version: int
) -> SecretEnvironment:
    """Restore every secret pinned in the target snapshot to that value.

    Append-only: each restored secret gets a NEW current version carrying the
    pinned snapshot value, and a NEW snapshot is recorded. Secrets created after
    the target snapshot are left untouched.
    """
    env = await _get_owned_environment(db, user_id, env_id)
    snapshot = await _get_snapshot(db, env_id, target_snapshot_version)
    entries_result = await db.execute(
        select(SecretSnapshotEntry).where(
            SecretSnapshotEntry.snapshot_id == snapshot.id
        )
    )
    for entry in entries_result.scalars().all():
        secret = await db.get(Secret, entry.secret_id)
        if secret is None or secret.environment_id != env_id:
            continue
        # Already at this pinned version → nothing to restore for this secret.
        if secret.current_version == entry.version and not secret.is_deleted:
            continue
        version_row = await db.get(SecretVersion, entry.secret_version_id)
        if version_row is None:
            continue
        await _append_version_from_ciphertext(
            db,
            secret,
            version_row.encrypted_value,
            version_row.value_hmac,
            f"Restore from snapshot v{target_snapshot_version}",
            user_id,
            is_rollback=True,
            rolled_back_from=entry.version,
        )
    await _record_snapshot(
        db,
        env,
        f"Rollback to v{target_snapshot_version}",
        user_id,
        is_rollback=True,
        rolled_back_from=target_snapshot_version,
    )
    await db.commit()
    await db.refresh(env)
    log_security_event(
        "environment_rolled_back",
        user_id=user_id,
        details={
            "environment_id": env_id,
            "to_snapshot": target_snapshot_version,
        },
    )
    return env


async def export_environment(
    db: AsyncSession,
    user_id: int,
    env_id: int,
    snapshot_version: Optional[int],
) -> dict[str, str]:
    """Return a {KEY: value} map for the current state or a historical snapshot.

    Audited — this is one of only two value-returning paths.
    """
    env = await _get_owned_environment(db, user_id, env_id)
    out: dict[str, str] = {}
    if snapshot_version is None:
        result = await db.execute(
            select(Secret).where(
                Secret.environment_id == env_id,
                Secret.is_deleted.is_(False),
                Secret.current_version > 0,
            )
        )
        for secret in result.scalars().all():
            row = await _get_version_row(db, secret.id, secret.current_version)
            if row is not None:
                out[secret.key] = _decrypt(row.encrypted_value)
    else:
        snapshot = await _get_snapshot(db, env_id, snapshot_version)
        entries_result = await db.execute(
            select(SecretSnapshotEntry).where(
                SecretSnapshotEntry.snapshot_id == snapshot.id
            )
        )
        for entry in entries_result.scalars().all():
            row = await db.get(SecretVersion, entry.secret_version_id)
            if row is not None:
                out[entry.secret_key] = _decrypt(row.encrypted_value)
    log_security_event(
        "environment_exported",
        user_id=user_id,
        details={
            "environment_id": env_id,
            "snapshot": snapshot_version,
            "key_count": len(out),
        },
    )
    return out
