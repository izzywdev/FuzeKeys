"""FKY-9: event schemas + dispatch stub semantics (no infra; in-memory SQLite)."""

import importlib.util
import json
import logging
from pathlib import Path

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session

from alembic.migration import MigrationContext
from alembic.operations import Operations
from app.events import consumer
from app.events.consumer import Outcome, dispatch
from app.events.schemas import EventType
from app.models.event_runtime import EventAggregateVersion, EventDeadLetter, EventInbox

USER = "usr_11111111-1111-4111-8111-111111111111"
ORG = "org_22222222-2222-4222-8222-222222222222"
EVENT_TABLES = [
    "event_inbox",
    "event_aggregate_versions",
    "event_dead_letters",
    "event_outbox",
]


def envelope(event_type, payload, aggregate_id, version=1, event_id="evt-00000001"):
    return {
        "eventId": event_id,
        "eventType": event_type,
        "schemaVersion": 2,
        "aggregateType": "user" if event_type.startswith("user.") else "org",
        "aggregateId": aggregate_id,
        "aggregateVersion": version,
        "occurredAt": "2026-10-13T12:00:00Z",
        "payload": payload,
    }


VALID = {
    "user.created": ({"userId": USER}, USER),
    "user.deleted": ({"userId": USER, "deletionMode": "soft"}, USER),
    "org.created": ({"orgId": ORG, "ownerUserId": USER}, ORG),
    "org.member.added": ({"orgId": ORG, "userId": USER, "role": "admin"}, ORG),
    "org.member.removed": ({"orgId": ORG, "userId": USER}, ORG),
}


@pytest.fixture()
def session():
    engine = sa.create_engine("sqlite:///:memory:")
    from app.database import Base

    Base.metadata.create_all(
        engine, tables=[Base.metadata.tables[name] for name in EVENT_TABLES]
    )
    with Session(engine) as s:
        yield s


@pytest.fixture()
def calls():
    return []


@pytest.fixture()
def handlers(calls):
    def record(_session, event):
        calls.append(event.event_type)

    return {t: record for t in EventType}


@pytest.mark.parametrize("event_type", sorted(VALID))
def test_all_five_event_types_validate_and_route(session, handlers, calls, event_type):
    payload, agg = VALID[event_type]
    out = dispatch(session, envelope(event_type, payload, agg), handlers)
    assert out is Outcome.APPLIED
    assert calls == [EventType(event_type)]


def test_all_five_handlers_are_registered():
    assert set(consumer.HANDLERS) == set(EventType)


def test_no_handler_for_known_type_writes_nothing(session):
    """Known type with an empty registry -> UNHANDLED, no partial state."""
    payload, agg = VALID["user.created"]
    assert dispatch(session, envelope("user.created", payload, agg), {}) is (
        Outcome.UNHANDLED
    )
    assert session.query(EventInbox).count() == 0
    assert session.query(EventAggregateVersion).count() == 0
    assert session.query(EventDeadLetter).count() == 0


def test_unknown_type_is_logged_without_pii_and_ignored(session, handlers, caplog):
    body = envelope("user.exploded", {"email": "alice@example.com"}, USER)
    with caplog.at_level(logging.INFO):
        out = dispatch(session, body, handlers)
    assert out is Outcome.IGNORED_UNKNOWN_TYPE
    assert session.query(EventInbox).count() == 0
    assert session.query(EventDeadLetter).count() == 0
    assert "alice@example.com" not in caplog.text
    assert USER not in caplog.text


@pytest.mark.parametrize(
    "raw",
    [
        b"not json",
        b"[]",
        b'{"eventType": "user.created"}',
        json.dumps(
            {
                **envelope("user.created", {"userId": USER}, USER),
                "occurredAt": "2026-10-13T12:00:00",
            }
        ),
        json.dumps(
            {**envelope("user.created", {"userId": USER}, USER), "aggregateVersion": 0}
        ),
        b"x" * (consumer.MAX_EVENT_BYTES + 1),
    ],
)
def test_malformed_envelope_is_dead_lettered_without_state(session, handlers, raw):
    assert dispatch(session, raw, handlers) is Outcome.DEAD_LETTERED
    dl = session.query(EventDeadLetter).one()
    assert dl.reason_code == "malformed_envelope"
    assert len(dl.payload_sha256) == 64
    assert session.query(EventInbox).count() == 0


@pytest.mark.parametrize(
    "event_type,payload,agg",
    [
        ("user.created", {}, USER),
        ("user.created", {"userId": ORG}, ORG),  # wrong prefix
        ("user.created", {"userId": "usr_nope"}, "usr_nope"),
        ("user.created", {"userId": "keys_" + USER}, "keys_" + USER),
        ("user.deleted", {"userId": USER, "deletionMode": "vaporise"}, USER),
        ("org.member.added", {"orgId": ORG}, ORG),  # missing userId
        ("org.created", {"orgId": ORG, "ownerUserId": ORG}, ORG),
        ("user.created", {"userId": USER}, "usr_33333333-3333-4333-8333-333333333333"),
    ],
)
def test_schema_violation_is_dead_lettered_without_state(
    session, handlers, calls, event_type, payload, agg
):
    assert dispatch(session, envelope(event_type, payload, agg), handlers) is (
        Outcome.DEAD_LETTERED
    )
    dl = session.query(EventDeadLetter).one()
    assert dl.reason_code == "schema_violation"
    assert dl.event_type == event_type
    assert calls == []
    assert session.query(EventInbox).count() == 0
    assert session.query(EventAggregateVersion).count() == 0


def test_dead_letter_never_stores_input_values(session, handlers):
    secret = "hunter2-secret-value"
    body = envelope("user.created", {"userId": secret}, secret)
    assert dispatch(session, body, handlers) is Outcome.DEAD_LETTERED
    dl = session.query(EventDeadLetter).one()
    assert secret not in dl.error_summary
    assert dl.event_id == "evt-00000001"


def test_duplicate_delivery_is_noop(session, handlers, calls):
    payload, agg = VALID["org.created"]
    body = envelope("org.created", payload, agg)
    assert dispatch(session, body, handlers) is Outcome.APPLIED
    assert dispatch(session, body, handlers) is Outcome.DUPLICATE
    assert len(calls) == 1
    assert session.query(EventInbox).count() == 1


def test_out_of_order_older_version_is_skipped(session, handlers, calls):
    payload, agg = VALID["org.member.added"]
    newer = envelope(
        "org.member.added", payload, agg, version=3, event_id="evt-0000000b"
    )
    older = envelope(
        "org.member.added", payload, agg, version=2, event_id="evt-0000000a"
    )
    assert dispatch(session, newer, handlers) is Outcome.APPLIED
    assert dispatch(session, older, handlers) is Outcome.STALE
    assert len(calls) == 1
    assert session.get(EventAggregateVersion, ("org", agg)).last_version == 3


def test_handler_failure_leaves_no_partial_state(session, caplog):
    def boom(sess, event):
        sess.add(
            EventDeadLetter(
                reason_code="partial",
                error_summary="x",
                payload_sha256="0" * 64,
            )
        )
        sess.flush()
        raise RuntimeError("row value alice@example.com")

    payload, agg = VALID["user.created"]
    with caplog.at_level(logging.INFO):
        out = dispatch(
            session,
            envelope("user.created", payload, agg),
            {EventType.USER_CREATED: boom},
        )
    assert out is Outcome.RETRY
    assert session.query(EventDeadLetter).count() == 0  # handler write rolled back
    assert session.query(EventInbox).count() == 0
    assert session.query(EventAggregateVersion).count() == 0
    assert "alice@example.com" not in caplog.text


def test_migration_creates_and_drops_the_event_tables():
    path = (
        Path(__file__).parents[1]
        / "alembic/versions/e2026evt01_event_consumer_runtime.py"
    )
    spec = importlib.util.spec_from_file_location("event_runtime_migration", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.down_revision == "d2026sms01"

    engine = sa.create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        with Operations.context(MigrationContext.configure(connection)):
            module.upgrade()
            assert set(EVENT_TABLES) <= set(sa.inspect(connection).get_table_names())
            module.downgrade()
            assert not set(EVENT_TABLES) & set(sa.inspect(connection).get_table_names())
