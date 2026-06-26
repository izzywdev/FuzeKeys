from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database import Base


class Agent(Base):
    """An MCP machine identity, bound to the user it acts on behalf of."""
    __tablename__ = "agents"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(120), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    token_hash = Column(String(255), nullable=False, index=True)  # hashed, never plaintext
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    scopes = relationship("AgentScope", back_populates="agent",
                          cascade="all, delete-orphan")


class AgentScope(Base):
    """One grant: what an agent may reach (an identity, a site, or a secret type)."""
    __tablename__ = "agent_scopes"

    id = Column(Integer, primary_key=True, index=True)
    agent_id = Column(Integer, ForeignKey("agents.id"), nullable=False, index=True)
    scope_type = Column(String(20), nullable=False)  # identity|site|secret_type
    scope_ref = Column(String(120), nullable=False)

    agent = relationship("Agent", back_populates="scopes")
