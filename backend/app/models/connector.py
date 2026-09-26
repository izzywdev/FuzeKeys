from sqlalchemy import JSON, Column, DateTime, Integer, String, UniqueConstraint
from sqlalchemy.sql import func

from app.database import Base


class ConnectorCredential(Base):
    """Non-secret connector metadata. OAuth material lives only in the vault."""

    __tablename__ = "connector_credentials"
    __table_args__ = (
        UniqueConstraint(
            "owner_subject", "provider", name="uq_connector_owner_provider"
        ),
    )

    id = Column(Integer, primary_key=True)
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
