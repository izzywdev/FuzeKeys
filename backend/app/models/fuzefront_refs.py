"""Local read-only reference index of FuzeFront ``user`` / ``org`` entities.

FuzeFront is the SINGLE WRITER of these entities (data-contract.json). These
tables are written ONLY by the event handlers in ``app/events/handlers.py`` and
are never exposed through a write path. They hold bare spine ids (``usr_<uuid>``
/ ``org_<uuid>``, lower-cased) and a role label -- no email, name or other
profile data -- so nothing here is PII.

They deliberately do NOT reuse the legacy local-auth ``users`` /
``organizations`` tables: those carry integer keys and NOT NULL credential
columns (email, hashed_password, master_key_hash) that an id-only event cannot
populate. No cross-aggregate foreign keys either: user and org events arrive on
independent aggregates in no guaranteed order.
"""

from sqlalchemy import Column, DateTime, Integer, PrimaryKeyConstraint, String
from sqlalchemy.sql import func

from app.database import Base

USER_ACTIVE = "active"
USER_INACTIVE = "inactive"  # soft-deleted upstream
USER_DELETED = "deleted"  # hard-deleted upstream (tombstone; row is retained)


class RefUser(Base):
    __tablename__ = "ref_users"

    user_id = Column(String(64), primary_key=True)  # bare usr_<uuid>
    status = Column(String(16), nullable=False, default=USER_ACTIVE)
    deletion_mode = Column(String(8), nullable=True)  # soft | hard
    deleted_at = Column(DateTime(timezone=True), nullable=True)
    source_version = Column(Integer, nullable=False)
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class RefOrg(Base):
    __tablename__ = "ref_orgs"

    org_id = Column(String(64), primary_key=True)  # bare org_<uuid>
    owner_user_id = Column(String(64), nullable=True)
    source_version = Column(Integer, nullable=False)
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class RefOrgMember(Base):
    __tablename__ = "ref_org_members"
    __table_args__ = (PrimaryKeyConstraint("org_id", "user_id"),)

    org_id = Column(String(64), nullable=False)
    user_id = Column(String(64), nullable=False, index=True)
    role = Column(String(64), nullable=False, default="member")
    source_version = Column(Integer, nullable=False)
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
