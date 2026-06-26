from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database import Base


class Organization(Base):
    """Top-level tenant (a company)."""
    __tablename__ = "organizations"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), nullable=False)
    slug = Column(String(100), nullable=False, unique=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    members = relationship("OrganizationMember", back_populates="organization",
                           cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Organization(id={self.id}, slug='{self.slug}')>"


class OrganizationMember(Base):
    """M:N membership of a user in an organization, with a role."""
    __tablename__ = "organization_members"
    __table_args__ = (UniqueConstraint("organization_id", "user_id",
                                       name="uq_org_member"),)

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    role = Column(String(20), nullable=False, default="member")  # owner|admin|member
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    organization = relationship("Organization", back_populates="members")

    def __repr__(self):
        return f"<OrganizationMember(org={self.organization_id}, user={self.user_id}, role={self.role})>"
