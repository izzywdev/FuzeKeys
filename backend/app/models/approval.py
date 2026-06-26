from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database import Base


class ApprovalRequest(Base):
    """A pending human approval for a sensitive secret release."""
    __tablename__ = "approval_requests"

    id = Column(Integer, primary_key=True, index=True)
    agent_id = Column(Integer, ForeignKey("agents.id"), nullable=False, index=True)
    resource_ref = Column(String(300), nullable=False)  # e.g. identity:42:card:7
    status = Column(String(20), nullable=False, default="pending")  # pending|approved|denied|expired
    requested_at = Column(DateTime(timezone=True), server_default=func.now())
    decided_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    decided_at = Column(DateTime(timezone=True), nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=True)

    agent = relationship("Agent")


class AuditLog(Base):
    """Append-only record of every access decision. Never stores the secret value."""
    __tablename__ = "audit_log"

    id = Column(Integer, primary_key=True, index=True)
    agent_id = Column(Integer, nullable=True, index=True)
    on_behalf_user_id = Column(Integer, nullable=True, index=True)
    identity_id = Column(Integer, nullable=True, index=True)
    resource_ref = Column(String(300), nullable=False)
    decision = Column(String(40), nullable=False)  # auto_release|approved|denied|scope_denied
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
