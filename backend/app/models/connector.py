from sqlalchemy import JSON, Column, DateTime, Index, Integer, String, UniqueConstraint, text
from sqlalchemy.sql import func

from app.database import Base


class ConnectorCredential(Base):
    """Non-secret connector metadata. OAuth material lives only in the vault."""

    __tablename__ = "connector_credentials"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "owner_subject",
            "provider",
            name="uq_connector_tenant_owner_provider",
        ),
        # SQL NULLs are distinct in a normal unique constraint. Personal
        # credentials deliberately use a NULL organization, so enforce their
        # owner/provider uniqueness with a partial unique index as well.
        Index(
            "uq_connector_personal_owner_provider",
            "owner_subject",
            "provider",
            unique=True,
            postgresql_where=text("tenant_id IS NULL"),
            sqlite_where=text("tenant_id IS NULL"),
        ),
    )

    id = Column(Integer, primary_key=True)
    # NULL legacy rows remain quarantined: no automatic tenant backfill.
    tenant_id = Column(String(255), nullable=True, index=True)
    owner_subject = Column(String(255), nullable=False, index=True)
    provider = Column(String(80), nullable=False)
    vault_ref = Column(String(500), nullable=False)
    identity_email = Column(String(320), nullable=True)
    scopes = Column(JSON, nullable=False, default=list)
    configuration = Column(JSON, nullable=False, default=dict)
    status = Column(String(32), nullable=False, default="connected")
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class ConnectorGrantIntent(Base):
    """Non-secret operator reconciliation outbox; runtime never applies grants."""

    __tablename__ = "connector_grant_intents"
    __table_args__ = (
        UniqueConstraint("tenant_id", "resource_key", name="uq_connector_grant_intent"),
    )
    id = Column(Integer, primary_key=True)
    tenant_id = Column(String(255), nullable=False)
    owner_subject = Column(String(255), nullable=False)
    provider = Column(String(80), nullable=False)
    resource_key = Column(String(80), nullable=False)
    desired_state = Column(String(16), nullable=False, default="present")
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
