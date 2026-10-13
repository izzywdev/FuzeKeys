"""Pydantic schemas for the FuzeFront events FuzeKeys consumes (envelope v2).

FuzeFront is the SINGLE WRITER of the ``user`` and ``org`` entities. FuzeKeys
only ever reads these events and keeps its own references; it never writes back.

Identifiers: ``usr_`` / ``org_`` are RESERVED spine prefixes owned by FuzeFront.
They are stored and carried BARE (``usr_<uuid>``) -- never re-namespaced as
``keys_usr_``. Format validation here is the structural L0 check; it is not a
capability and grants nothing (authorization comes from the authenticated
transport). TODO(FKY-10): swap the regexes for ``fuzefront_identity.assert_ref``
once that package is a dependency (gate_identifier A1/A2).

Compatibility: unknown extra fields are IGNORED (the producer may add fields
without breaking us) and are never persisted, so a producer adding a PII field
cannot leak it into FuzeKeys storage or logs. Missing/invalid required fields
reject.

PII: these payloads carry identifiers and a role label only -- no email, name or
other profile data -- so nothing here may be logged or stored beyond metadata.
"""

import re
from datetime import datetime
from enum import Enum
from typing import Annotated, Any, Dict, Optional, Type, Union

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    model_validator,
)
from pydantic.alias_generators import to_camel

SCHEMA_VERSION = 2

_UUID = r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
USER_REF_RE = re.compile(rf"^usr_{_UUID}$")
ORG_REF_RE = re.compile(rf"^org_{_UUID}$")


def _check(pattern: "re.Pattern[str]", kind: str):
    def validator(value: str) -> str:
        # Never echo the offending value (it is attacker-controlled input).
        if not pattern.match(value):
            raise ValueError(f"not a valid bare {kind} reference")
        return value.lower()

    return validator


UserRef = Annotated[
    str,
    StringConstraints(max_length=64),
    AfterValidator(_check(USER_REF_RE, "usr_")),
]
OrgRef = Annotated[
    str,
    StringConstraints(max_length=64),
    AfterValidator(_check(ORG_REF_RE, "org_")),
]


class EventType(str, Enum):
    USER_CREATED = "user.created"
    USER_DELETED = "user.deleted"
    ORG_CREATED = "org.created"
    ORG_MEMBER_ADDED = "org.member.added"
    ORG_MEMBER_REMOVED = "org.member.removed"


class EventContractError(ValueError):
    """Contract violation with a fixed, value-free message (safe to persist/log)."""


class DeletionMode(str, Enum):
    """Both forms must be honoured by the on-delete handler (data-contract)."""

    SOFT = "soft"
    HARD = "hard"


class _Model(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        extra="ignore",
        frozen=True,
    )


# --- payloads (the bare ids) -------------------------------------------------


class UserCreatedPayload(_Model):
    user_id: UserRef


class UserDeletedPayload(_Model):
    user_id: UserRef
    deletion_mode: DeletionMode = DeletionMode.HARD


class OrgCreatedPayload(_Model):
    org_id: OrgRef
    owner_user_id: Optional[UserRef] = None


class OrgMemberAddedPayload(_Model):
    org_id: OrgRef
    user_id: UserRef
    role: Optional[
        Annotated[str, StringConstraints(min_length=1, max_length=64)]
    ] = None


class OrgMemberRemovedPayload(_Model):
    org_id: OrgRef
    user_id: UserRef


PAYLOAD_MODELS: Dict[EventType, Type[_Model]] = {
    EventType.USER_CREATED: UserCreatedPayload,
    EventType.USER_DELETED: UserDeletedPayload,
    EventType.ORG_CREATED: OrgCreatedPayload,
    EventType.ORG_MEMBER_ADDED: OrgMemberAddedPayload,
    EventType.ORG_MEMBER_REMOVED: OrgMemberRemovedPayload,
}

# event type -> (aggregate type, payload attribute that must equal aggregateId)
AGGREGATES: Dict[EventType, tuple] = {
    EventType.USER_CREATED: ("user", "user_id"),
    EventType.USER_DELETED: ("user", "user_id"),
    EventType.ORG_CREATED: ("org", "org_id"),
    EventType.ORG_MEMBER_ADDED: ("org", "org_id"),
    EventType.ORG_MEMBER_REMOVED: ("org", "org_id"),
}

Payload = Union[
    UserCreatedPayload,
    UserDeletedPayload,
    OrgCreatedPayload,
    OrgMemberAddedPayload,
    OrgMemberRemovedPayload,
]


# --- envelope ----------------------------------------------------------------


class EventEnvelope(_Model):
    """Envelope v2 as produced by FuzeFront's outbox.

    ``aggregate_version`` is bumped by the producer on EVERY change to the
    aggregate; it is the ordering/version-guard key (not wall-clock time).
    ``event_id`` is the idempotency key (inbox dedupe).
    """

    event_id: Annotated[str, StringConstraints(min_length=8, max_length=64)]
    event_type: Annotated[str, StringConstraints(max_length=120)]
    schema_version: int = Field(ge=1)
    aggregate_type: Annotated[str, StringConstraints(max_length=32)]
    aggregate_id: Annotated[str, StringConstraints(max_length=64)]
    aggregate_version: int = Field(ge=1)
    occurred_at: datetime
    payload: Dict[str, Any]

    @model_validator(mode="after")
    def _occurred_at_is_aware(self) -> "EventEnvelope":
        if self.occurred_at.tzinfo is None:
            raise ValueError("occurredAt must carry a timezone")
        return self


class ConsumedEvent(_Model):
    """A fully validated event: envelope + typed payload, cross-checked."""

    event_id: str
    event_type: EventType
    aggregate_type: str
    aggregate_id: str
    aggregate_version: int
    occurred_at: datetime
    payload: Payload


def is_known_event_type(event_type: str) -> bool:
    return event_type in {member.value for member in EventType}


def validate_event(envelope: EventEnvelope) -> ConsumedEvent:
    """Validate ``envelope.payload`` for its (known) event type.

    Raises ``EventContractError``/``pydantic.ValidationError`` on any violation; the
    caller dead-letters. Cross-checks that the envelope's aggregate matches the
    payload, so a forged envelope cannot make us version-guard the wrong row.
    """
    if envelope.schema_version != SCHEMA_VERSION:
        raise EventContractError("unsupported schemaVersion")
    if not is_known_event_type(envelope.event_type):
        raise EventContractError("unknown eventType")
    event_type = EventType(envelope.event_type)
    payload = PAYLOAD_MODELS[event_type].model_validate(envelope.payload)
    aggregate_type, attr = AGGREGATES[event_type]
    if envelope.aggregate_type != aggregate_type:
        raise EventContractError("aggregateType does not match eventType")
    if envelope.aggregate_id.lower() != getattr(payload, attr):
        raise EventContractError("aggregateId does not match payload")
    return ConsumedEvent(
        event_id=envelope.event_id,
        event_type=event_type,
        aggregate_type=aggregate_type,
        aggregate_id=getattr(payload, attr),
        aggregate_version=envelope.aggregate_version,
        occurred_at=envelope.occurred_at,
        payload=payload,  # type: ignore[arg-type]
    )
