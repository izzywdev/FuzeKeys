"""Consumer interface + single dispatch stub for FuzeFront events (FKY-9).

Scope: the INTERFACE and the dispatch/reject/ignore semantics only. NO handler
bodies exist -- ``HANDLERS`` is empty and the five handlers land in FKY-10.

Dispatch contract (``dispatch``):

  1. malformed envelope / unparseable / oversize   -> dead-letter, no state change
  2. unknown ``eventType``                         -> log (no PII) + IGNORE
  3. known type, payload violates its schema       -> dead-letter, no state change
  4. duplicate ``eventId`` (inbox)                 -> DUPLICATE, no-op
  5. ``aggregateVersion`` <= last applied          -> STALE, no-op (out-of-order)
  6. no handler registered (current state)         -> UNHANDLED, nothing written
  7. handler registered: handler + inbox row + version bump run in ONE savepoint,
     so a handler failure leaves NO partial state -> RETRY (transient)

The caller owns the transaction (it commits after ``dispatch`` returns) and maps
the outcome to the ingress response (see docs/fuzefront-event-contract.md).

PII / logging: only ``eventId``, a sanitised ``eventType``, aggregate version and
the outcome are ever logged or persisted. Payload values, ids from the payload
and exception messages (which can embed row values) are never logged.
"""

import hashlib
import json
import logging
import re
from enum import Enum
from typing import Any, Callable, Dict, Mapping, Optional, Union

from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.events.schemas import (
    ConsumedEvent,
    EventContractError,
    EventEnvelope,
    EventType,
    is_known_event_type,
    validate_event,
)
from app.models.event_runtime import EventAggregateVersion, EventDeadLetter, EventInbox

logger = logging.getLogger(__name__)

MAX_EVENT_BYTES = 64 * 1024
_SAFE_TOKEN = re.compile(r"^[A-Za-z0-9._-]{1,64}$")

# A handler applies one validated event to local state using the given session.
# It must be idempotent and must NOT commit (dispatch owns the savepoint).
EventHandler = Callable[[Session, ConsumedEvent], None]

# FKY-10 registers the five handlers here. Empty by design in FKY-9.
HANDLERS: Dict[EventType, EventHandler] = {}


class Outcome(str, Enum):
    APPLIED = "applied"
    DUPLICATE = "duplicate"
    STALE = "stale"
    IGNORED_UNKNOWN_TYPE = "ignored_unknown_type"
    DEAD_LETTERED = "dead_lettered"
    UNHANDLED = "unhandled"  # valid event, no handler registered yet (FKY-9)
    RETRY = "retry"  # handler failed; nothing applied; redeliver


def _log_token(value: Any) -> str:
    """Sanitise an untrusted string before logging (no log injection, no PII)."""
    if isinstance(value, str) and _SAFE_TOKEN.match(value):
        return value
    return "<invalid>"


def _sha256(raw: Union[bytes, str, Mapping[str, Any]]) -> str:
    if isinstance(raw, bytes):
        data = raw
    elif isinstance(raw, str):
        data = raw.encode("utf-8", "replace")
    else:
        data = json.dumps(raw, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def _summarise(exc: Exception) -> str:
    """Field locations + error types only -- never input values."""
    if isinstance(exc, ValidationError):
        parts = [
            "{}:{}".format(
                ".".join(str(p) for p in err["loc"]) or "<root>", err["type"]
            )
            for err in exc.errors()[:20]
        ]
        return "; ".join(parts)
    if isinstance(exc, EventContractError):
        return str(exc)
    return "invalid_event"


def _dead_letter(
    session: Session,
    raw: Union[bytes, str, Mapping[str, Any]],
    reason_code: str,
    exc: Exception,
    event_id: Optional[str] = None,
    event_type: Optional[str] = None,
) -> Outcome:
    session.add(
        EventDeadLetter(
            event_id=event_id if _SAFE_TOKEN.match(event_id or "") else None,
            event_type=event_type if _SAFE_TOKEN.match(event_type or "") else None,
            reason_code=reason_code,
            error_summary=_summarise(exc),
            payload_sha256=_sha256(raw),
        )
    )
    session.flush()
    logger.warning(
        "event dead-lettered",
        extra={
            "event_id": _log_token(event_id),
            "event_type": _log_token(event_type),
            "reason": reason_code,
        },
    )
    return Outcome.DEAD_LETTERED


def dispatch(
    session: Session,
    raw: Union[bytes, str, Mapping[str, Any]],
    handlers: Optional[Mapping[EventType, EventHandler]] = None,
) -> Outcome:
    """Validate and route one inbound event. See module docstring."""
    registry = HANDLERS if handlers is None else handlers

    # 1. parse + envelope
    try:
        if isinstance(raw, (bytes, str)):
            if len(raw) > MAX_EVENT_BYTES:
                raise EventContractError("event too large")
            body = json.loads(raw)
        else:
            body = dict(raw)
        envelope = EventEnvelope.model_validate(body)
    except (ValueError, TypeError) as exc:  # JSONDecodeError/ValidationError
        return _dead_letter(session, raw, "malformed_envelope", exc)

    # 2. unknown type: ignore (forward compatible with new producer events)
    if not is_known_event_type(envelope.event_type):
        logger.info(
            "event ignored: unknown type",
            extra={
                "event_id": _log_token(envelope.event_id),
                "event_type": _log_token(envelope.event_type),
            },
        )
        return Outcome.IGNORED_UNKNOWN_TYPE

    # 3. payload schema
    try:
        event = validate_event(envelope)
    except (ValueError, TypeError) as exc:
        return _dead_letter(
            session,
            raw,
            "schema_violation",
            exc,
            event_id=envelope.event_id,
            event_type=envelope.event_type,
        )

    meta = {
        "event_id": event.event_id,
        "event_type": event.event_type.value,
        "aggregate_version": event.aggregate_version,
    }

    # 4. idempotency
    if session.query(EventInbox.id).filter_by(event_id=event.event_id).first():
        logger.info("event duplicate: no-op", extra=meta)
        return Outcome.DUPLICATE

    # 5. version guard
    last = session.get(
        EventAggregateVersion, (event.aggregate_type, event.aggregate_id)
    )
    if last is not None and event.aggregate_version <= last.last_version:
        logger.info("event stale: older than applied version", extra=meta)
        return Outcome.STALE

    # 6. no handler yet (FKY-9): write NOTHING so FKY-10 can apply it on redelivery
    handler = registry.get(event.event_type)
    if handler is None:
        logger.info("event valid but no handler registered", extra=meta)
        return Outcome.UNHANDLED

    # 7. atomic apply: handler + inbox + version bump, or nothing
    try:
        with session.begin_nested():
            handler(session, event)
            session.add(
                EventInbox(
                    event_id=event.event_id,
                    event_type=event.event_type.value,
                    aggregate_type=event.aggregate_type,
                    aggregate_id=event.aggregate_id,
                    aggregate_version=event.aggregate_version,
                    outcome="applied",
                )
            )
            if last is None:
                session.add(
                    EventAggregateVersion(
                        aggregate_type=event.aggregate_type,
                        aggregate_id=event.aggregate_id,
                        last_version=event.aggregate_version,
                    )
                )
            else:
                last.last_version = event.aggregate_version  # type: ignore[assignment]
            session.flush()
    except IntegrityError:
        # A concurrent delivery of the same event won the unique(event_id) race.
        logger.info("event duplicate: lost insert race", extra=meta)
        return Outcome.DUPLICATE
    except Exception as exc:  # noqa: BLE001 - never leak exc text (may hold PII)
        logger.error(
            "event handler failed; rolled back",
            extra={**meta, "error_type": type(exc).__name__},
        )
        return Outcome.RETRY

    logger.info("event applied", extra=meta)
    return Outcome.APPLIED
