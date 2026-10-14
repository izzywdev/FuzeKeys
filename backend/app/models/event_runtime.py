"""Event-consumer runtime tables: inbox, version guard, dead letters, outbox.

FKY-9 scaffolding for consuming FuzeFront's ``user`` / ``org`` events (see
``data-contract.json``). These tables hold NO payload bodies and NO PII:

  - ``event_inbox``              idempotency: one row per applied/skipped event id.
  - ``event_aggregate_versions`` version guard: highest ``aggregateVersion``
                                 applied per (aggregate_type, aggregate_id).
  - ``event_dead_letters``       rejected events: reason code + field locations +
                                 payload SHA-256 only. The raw body is NOT stored
                                 (it is attacker-controlled and may carry PII);
                                 replay = ask FuzeFront to redeliver.
  - ``event_outbox``             transactional outbox for events FuzeKeys itself
                                 emits (none declared yet -- ``emits`` is empty in
                                 data-contract.json -- the table exists so the
                                 first emitter writes in the same transaction as
                                 its state change rather than calling a producer).
"""

from sqlalchemy import (
    Column,
    DateTime,
    Index,
    Integer,
    PrimaryKeyConstraint,
    String,
    Text,
)
from sqlalchemy.sql import func

from app.database import Base


class EventInbox(Base):
    __tablename__ = "event_inbox"

    id = Column(Integer, primary_key=True)
    # Producer-assigned event id: the dedupe key. UNIQUE makes the dedupe
    # race-safe (a concurrent duplicate insert fails instead of double-applying).
    event_id = Column(String(64), nullable=False, unique=True)
    event_type = Column(String(64), nullable=False)
    aggregate_type = Column(String(32), nullable=False)
    aggregate_id = Column(String(64), nullable=False)
    aggregate_version = Column(Integer, nullable=False)
    # "applied" | "stale" (older than the version already applied; skipped)
    outcome = Column(String(16), nullable=False)
    received_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class EventAggregateVersion(Base):
    __tablename__ = "event_aggregate_versions"
    __table_args__ = (PrimaryKeyConstraint("aggregate_type", "aggregate_id"),)

    aggregate_type = Column(String(32), nullable=False)
    aggregate_id = Column(String(64), nullable=False)
    last_version = Column(Integer, nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class EventDeadLetter(Base):
    __tablename__ = "event_dead_letters"

    id = Column(Integer, primary_key=True)
    # Untrusted and possibly absent/unparseable -> nullable, length-bounded.
    event_id = Column(String(64), nullable=True, index=True)
    event_type = Column(String(64), nullable=True)
    # "malformed_envelope" | "schema_violation"
    reason_code = Column(String(32), nullable=False)
    # Field locations + validator error types only; never input values.
    error_summary = Column(Text, nullable=False)
    payload_sha256 = Column(String(64), nullable=False)
    received_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class EventOutbox(Base):
    __tablename__ = "event_outbox"
    __table_args__ = (Index("ix_event_outbox_unpublished", "published_at", "id"),)

    id = Column(Integer, primary_key=True)
    event_id = Column(String(64), nullable=False, unique=True)
    event_type = Column(String(64), nullable=False)
    aggregate_type = Column(String(32), nullable=False)
    aggregate_id = Column(String(64), nullable=False)
    aggregate_version = Column(Integer, nullable=False)
    payload = Column(Text, nullable=False)  # JSON, public snapshot only
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    published_at = Column(DateTime(timezone=True), nullable=True)
