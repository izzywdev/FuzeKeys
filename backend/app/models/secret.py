"""Secret versioning and environment-grouped rollback models.

These tables add first-class, immutable version history to secrets and group
them into named environments (Dev / Prod / ...) that keep their own snapshot
history, so an individual secret — or a whole environment — can be rolled back
to a prior value.

Security: secret values are NEVER stored in plaintext here. `SecretVersion`
holds only Fernet ciphertext produced with the same ``CREDENTIAL_ENCRYPTION_KEY``
regime as the credentials API (see ``app.services.secret_versioning``), and the
snapshot/entry tables reference version rows by id — they never copy a value.

Typed with SQLAlchemy 2.0 ``Mapped``/``mapped_column`` so instance attributes
carry their scalar Python types (not ``Column[...]``) under mypy.
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.database import Base


class SecretEnvironment(Base):
    """A named, user-owned group of secrets (e.g. Dev, Prod).

    Owns a monotonic snapshot history (``current_snapshot_version``). Rolling the
    environment back restores every member secret to the version pinned in a
    chosen snapshot.
    """

    __tablename__ = "secret_environments"
    __table_args__ = (
        UniqueConstraint("user_id", "name", name="uq_secret_env_user_name"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Optional org scoping, mirrors Identity.org_id (nullable — no secrets here).
    org_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("organizations.id"), nullable=True
    )

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    # Highest snapshot number recorded for this environment (0 == none yet).
    current_snapshot_version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )

    created_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), onupdate=func.now()
    )

    secrets: Mapped[list["Secret"]] = relationship(
        "Secret",
        back_populates="environment",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    snapshots: Mapped[list["EnvironmentSnapshot"]] = relationship(
        "EnvironmentSnapshot",
        back_populates="environment",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    def __repr__(self):
        return (
            f"<SecretEnvironment(id={self.id}, name='{self.name}', "
            f"user_id={self.user_id}, snapshot_v={self.current_snapshot_version})>"
        )


class Secret(Base):
    """A named secret (env-var-like key) within an environment.

    ``current_version`` points at the active ``SecretVersion.version``. Soft
    deletes (``is_deleted``) keep the key resolvable for historical snapshots.
    """

    __tablename__ = "secrets"
    __table_args__ = (
        UniqueConstraint("environment_id", "key", name="uq_secret_env_key"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    environment_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("secret_environments.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    key: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    current_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    created_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), onupdate=func.now()
    )

    environment: Mapped["SecretEnvironment"] = relationship(
        "SecretEnvironment", back_populates="secrets"
    )
    versions: Mapped[list["SecretVersion"]] = relationship(
        "SecretVersion",
        back_populates="secret",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    def __repr__(self):
        return (
            f"<Secret(id={self.id}, key='{self.key}', env={self.environment_id}, "
            f"v={self.current_version}, deleted={self.is_deleted})>"
        )


class SecretVersion(Base):
    """An immutable historical value for a secret.

    Append-only: a value change or a rollback appends a new row; existing rows
    are never mutated or deleted. ``encrypted_value`` is Fernet ciphertext.
    """

    __tablename__ = "secret_versions"
    __table_args__ = (
        UniqueConstraint("secret_id", "version", name="uq_secret_version"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    secret_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("secrets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)

    # Fernet ciphertext — NEVER plaintext.
    encrypted_value: Mapped[str] = mapped_column(Text, nullable=False)
    # Keyed HMAC of the plaintext, for no-op change detection only. Never served.
    value_hmac: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    change_comment: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    is_rollback: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    rolled_back_from_version: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True
    )

    created_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    created_by_user_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    secret: Mapped["Secret"] = relationship("Secret", back_populates="versions")

    def __repr__(self):
        return (
            f"<SecretVersion(secret_id={self.secret_id}, v={self.version}, "
            f"rollback={self.is_rollback})>"
        )


class EnvironmentSnapshot(Base):
    """An immutable snapshot of an environment: which version of each secret was
    active at a point in time. Rolling the environment back to a snapshot
    restores those pinned values.
    """

    __tablename__ = "environment_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "environment_id", "snapshot_version", name="uq_env_snapshot_version"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    environment_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("secret_environments.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    snapshot_version: Mapped[int] = mapped_column(Integer, nullable=False)
    label: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    is_rollback: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    rolled_back_from_snapshot: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True
    )

    created_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    created_by_user_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    environment: Mapped["SecretEnvironment"] = relationship(
        "SecretEnvironment", back_populates="snapshots"
    )
    entries: Mapped[list["SecretSnapshotEntry"]] = relationship(
        "SecretSnapshotEntry",
        back_populates="snapshot",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    def __repr__(self):
        return (
            f"<EnvironmentSnapshot(env={self.environment_id}, "
            f"v={self.snapshot_version}, rollback={self.is_rollback})>"
        )


class SecretSnapshotEntry(Base):
    """One pin inside a snapshot: secret -> the version active at snapshot time.

    ``secret_key`` and ``version`` are denormalized so an export of a historical
    snapshot still resolves even if the secret was later renamed/soft-deleted.
    """

    __tablename__ = "secret_snapshot_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    snapshot_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("environment_snapshots.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    secret_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("secrets.id", ondelete="CASCADE"), nullable=False
    )
    secret_version_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("secret_versions.id", ondelete="CASCADE"), nullable=False
    )
    secret_key: Mapped[str] = mapped_column(String(255), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)

    snapshot: Mapped["EnvironmentSnapshot"] = relationship(
        "EnvironmentSnapshot", back_populates="entries"
    )

    def __repr__(self):
        return (
            f"<SecretSnapshotEntry(snapshot={self.snapshot_id}, "
            f"key='{self.secret_key}', v={self.version})>"
        )
