"""Verified platform identity binding; no session credentials are persisted."""

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.sql import func

from app.database import Base


class PlatformIdentity(Base):
    __tablename__ = "platform_identities"
    __table_args__ = (
        UniqueConstraint("subject", "tenant", name="uq_platform_subject_tenant"),
    )

    user_id = Column(Integer, ForeignKey("users.id"), primary_key=True)
    subject = Column(String(255), nullable=False)
    tenant = Column(String(255), nullable=False)
    verified_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
