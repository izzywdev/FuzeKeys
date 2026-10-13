"""FKY-10: the five FuzeFront event handlers through the real ``dispatch``.

For every event type: apply / replay (duplicate no-op) / out-of-order (stale
discard) / delete tombstone + cascade / handler failure rollback (RETRY, no ack,
redelivers cleanly). In-memory SQLite, no infra.
"""

import logging

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session

import app.models  # noqa: F401  (register every table on Base.metadata)
from app.database import Base
from app.events import consumer
from app.events.consumer import Outcome, dispatch
from app.events.schemas import EventType
from app.models.connector import ConnectorCredential, ConnectorGrantIntent
from app.models.event_runtime import EventAggregateVersion, EventInbox
from app.models.fuzefront_refs import RefOrg, RefOrgMember, RefUser
from app.models.platform_identity import PlatformIdentity
from app.models.user import User

USER = "usr_11111111-1111-4111-8111-111111111111"
USER2 = "usr_44444444-4444-4444-8444-444444444444"
ORG = "org_22222222-2222-4222-8222-222222222222"


def env(event_type, payload, aggregate_id, version, event_id):
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


def user_created(version=1, event_id="evt-uc-0001", user=USER):
    return env("user.created", {"userId": user}, user, version, event_id)


def user_deleted(mode="hard", version=2, event_id="evt-ud-0001", user=USER):
    return env(
        "user.deleted", {"userId": user, "deletionMode": mode}, user, version, event_id
    )


def org_created(version=1, event_id="evt-oc-0001", owner=USER):
    return env(
        "org.created", {"orgId": ORG, "ownerUserId": owner}, ORG, version, event_id
    )


def member_added(version=2, event_id="evt-ma-0001", user=USER, role="admin"):
    payload = {"orgId": ORG, "userId": user}
    if role is not None:
        payload["role"] = role
    return env("org.member.added", payload, ORG, version, event_id)


def member_removed(version=3, event_id="evt-mr-0001", user=USER):
    return env(
        "org.member.removed", {"orgId": ORG, "userId": user}, ORG, version, event_id
    )


@pytest.fixture()
def session():
    engine = sa.create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


def counts(session):
    return (
        session.query(EventInbox).count(),
        session.query(EventAggregateVersion).count(),
    )


# ---- user.created -----------------------------------------------------------


def test_user_created_applies_upserts_and_replays_as_noop(session):
    assert dispatch(session, user_created()) is Outcome.APPLIED
    row = session.get(RefUser, USER)
    assert (row.status, row.source_version) == ("active", 1)
    assert dispatch(session, user_created()) is Outcome.DUPLICATE
    assert session.query(RefUser).count() == 1
    assert counts(session) == (1, 1)


def test_user_created_newer_version_with_new_event_id_is_idempotent_upsert(session):
    dispatch(session, user_created(version=1))
    assert dispatch(session, user_created(version=2, event_id="evt-uc-0002")) is (
        Outcome.APPLIED
    )
    assert session.query(RefUser).count() == 1
    assert session.get(RefUser, USER).source_version == 2


def test_user_created_out_of_order_is_discarded(session):
    dispatch(session, user_created(version=5, event_id="evt-uc-0005"))
    assert dispatch(session, user_created(version=3, event_id="evt-uc-0003")) is (
        Outcome.STALE
    )
    assert session.get(RefUser, USER).source_version == 5
    assert session.get(EventAggregateVersion, ("user", USER)).last_version == 5


# ---- user.deleted -----------------------------------------------------------


def seed_user_dependents(session):
    session.add(
        User(
            id=1,
            email="a@example.com",
            username="a",
            hashed_password="x",
            master_key_hash="y",
        )
    )
    session.flush()
    session.add(PlatformIdentity(user_id=1, subject=USER, tenant=ORG))
    session.add(
        ConnectorCredential(
            tenant_id=ORG,
            owner_subject=USER,
            provider="google-gmail",
            vault_ref="secret/vault/ref",
            identity_email="a@example.com",
            status="connected",
        )
    )
    session.add(
        ConnectorCredential(
            tenant_id=ORG,
            owner_subject=USER2,
            provider="google-gmail",
            vault_ref="secret/vault/other",
            identity_email="b@example.com",
            status="connected",
        )
    )
    session.add(
        ConnectorGrantIntent(
            tenant_id=ORG,
            owner_subject=USER,
            provider="google-gmail",
            resource_key="k1",
            desired_state="present",
        )
    )
    session.flush()


@pytest.mark.parametrize("mode,status", [("hard", "deleted"), ("soft", "inactive")])
def test_user_deleted_tombstones_and_cascades(session, mode, status):
    seed_user_dependents(session)
    dispatch(session, user_created(version=1))
    dispatch(session, org_created())
    dispatch(session, member_added())
    assert session.query(RefOrgMember).count() == 1

    assert dispatch(session, user_deleted(mode=mode)) is Outcome.APPLIED

    row = session.get(RefUser, USER)  # tombstone retained, never hard-deleted
    assert (row.status, row.deletion_mode) == (status, mode)
    assert row.deleted_at is not None
    assert session.query(PlatformIdentity).count() == 0  # access binding revoked
    cred = session.query(ConnectorCredential).filter_by(owner_subject=USER).one()
    assert cred.status == "owner_deleted"
    assert cred.identity_email is None
    assert cred.vault_ref == "secret/vault/ref"  # kept for the Vault purge
    intent = session.query(ConnectorGrantIntent).one()
    assert intent.desired_state == "absent"
    assert session.query(RefOrgMember).count() == 0
    # other users untouched
    other = session.query(ConnectorCredential).filter_by(owner_subject=USER2).one()
    assert (other.status, other.identity_email) == ("connected", "b@example.com")


def test_user_deleted_replay_and_out_of_order(session):
    dispatch(session, user_created(version=1))
    assert dispatch(session, user_deleted(version=2)) is Outcome.APPLIED
    assert dispatch(session, user_deleted(version=2)) is Outcome.DUPLICATE
    # a late, older created must not resurrect the tombstone
    assert dispatch(session, user_created(version=1, event_id="evt-uc-late")) is (
        Outcome.STALE
    )
    assert session.get(RefUser, USER).status == "deleted"


def test_user_deleted_before_created_records_tombstone(session):
    assert dispatch(session, user_deleted(version=4)) is Outcome.APPLIED
    assert session.get(RefUser, USER).status == "deleted"


def test_member_add_for_deleted_user_does_not_grant_membership(session):
    dispatch(session, user_created(version=1))
    dispatch(session, user_deleted(version=2))
    assert dispatch(session, member_added()) is Outcome.APPLIED
    assert session.query(RefOrgMember).count() == 0


# ---- org.created ------------------------------------------------------------


def test_org_created_apply_replay_out_of_order(session):
    assert dispatch(session, org_created(version=2, event_id="evt-oc-0002")) is (
        Outcome.APPLIED
    )
    row = session.get(RefOrg, ORG)
    assert (row.owner_user_id, row.source_version) == (USER, 2)
    assert dispatch(session, org_created(version=2, event_id="evt-oc-0002")) is (
        Outcome.DUPLICATE
    )
    assert dispatch(session, org_created(version=1, event_id="evt-oc-0001")) is (
        Outcome.STALE
    )
    assert session.query(RefOrg).count() == 1
    assert session.get(RefOrg, ORG).source_version == 2


def test_org_created_without_owner(session):
    body = env("org.created", {"orgId": ORG}, ORG, 1, "evt-oc-noown")
    assert dispatch(session, body) is Outcome.APPLIED
    assert session.get(RefOrg, ORG).owner_user_id is None


# ---- org.member.added / removed --------------------------------------------


def test_member_added_apply_replay_and_role_update(session):
    assert dispatch(session, member_added(version=2)) is Outcome.APPLIED
    assert session.get(RefOrgMember, (ORG, USER)).role == "admin"
    assert dispatch(session, member_added(version=2)) is Outcome.DUPLICATE
    assert session.query(RefOrgMember).count() == 1
    assert dispatch(
        session, member_added(version=3, event_id="evt-ma-0003", role="viewer")
    ) is (Outcome.APPLIED)
    assert session.get(RefOrgMember, (ORG, USER)).role == "viewer"
    assert session.query(RefOrgMember).count() == 1


def test_member_added_defaults_role_to_member(session):
    dispatch(session, member_added(role=None))
    assert session.get(RefOrgMember, (ORG, USER)).role == "member"


def test_member_added_out_of_order_discarded(session):
    dispatch(session, member_added(version=5, event_id="evt-ma-0005", role="owner"))
    assert dispatch(
        session, member_added(version=4, event_id="evt-ma-0004", role="member")
    ) is (Outcome.STALE)
    assert session.get(RefOrgMember, (ORG, USER)).role == "owner"


def test_member_removed_apply_replay_and_out_of_order(session):
    dispatch(session, member_added(version=2))
    assert dispatch(session, member_removed(version=4)) is Outcome.APPLIED
    assert session.query(RefOrgMember).count() == 0
    assert dispatch(session, member_removed(version=4)) is Outcome.DUPLICATE
    # a late older add must not resurrect the removed member
    assert dispatch(
        session, member_added(version=3, event_id="evt-ma-late", role="member")
    ) is (Outcome.STALE)
    assert session.query(RefOrgMember).count() == 0


def test_member_removed_when_never_added_is_a_noop_but_acked(session):
    assert dispatch(session, member_removed(version=2)) is Outcome.APPLIED
    assert session.query(RefOrgMember).count() == 0
    assert counts(session) == (1, 1)


def test_other_members_unaffected_by_removal(session):
    dispatch(session, member_added(version=2))
    dispatch(session, member_added(version=3, event_id="evt-ma-u2", user=USER2))
    dispatch(session, member_removed(version=4))
    assert [m.user_id for m in session.query(RefOrgMember)] == [USER2]


# ---- handler failure: rollback, no ack, redelivery --------------------------

CASES = [
    ("user.created", user_created),
    ("user.deleted", user_deleted),
    ("org.created", org_created),
    ("org.member.added", member_added),
    ("org.member.removed", member_removed),
]


@pytest.mark.parametrize("event_type,build", CASES)
def test_handler_failure_rolls_back_returns_retry_and_redelivers(
    session, caplog, event_type, build
):
    real = consumer.HANDLERS[EventType(event_type)]
    if event_type == "org.member.removed":
        dispatch(session, member_added(version=1, event_id="evt-ma-seed"))
    if event_type == "user.deleted":
        seed_user_dependents(session)
    before = counts(session)

    def fail_after_write(sess, event):
        real(sess, event)  # real writes happen, then the unit fails
        raise RuntimeError("row value alice@example.com")

    snapshot = _state(session)
    with caplog.at_level(logging.INFO):
        out = dispatch(
            session, build(version=9), {EventType(event_type): fail_after_write}
        )
    assert out is Outcome.RETRY
    assert counts(session) == before  # no inbox row, no version bump: NOT acked
    assert _state(session) == snapshot  # handler writes rolled back
    assert "alice@example.com" not in caplog.text

    # redelivery with the healthy handler now applies
    assert dispatch(session, build(version=9)) is Outcome.APPLIED
    assert counts(session)[0] == before[0] + 1


def _state(session):
    return (
        [(r.user_id, r.status, r.source_version) for r in session.query(RefUser)],
        [(r.org_id, r.source_version) for r in session.query(RefOrg)],
        [(r.org_id, r.user_id, r.role) for r in session.query(RefOrgMember)],
        [
            (c.id, c.status, c.identity_email)
            for c in session.query(ConnectorCredential)
        ],
        [(i.id, i.desired_state) for i in session.query(ConnectorGrantIntent)],
        session.query(PlatformIdentity).count(),
    )


# ---- PII / logging ----------------------------------------------------------


def test_handlers_never_log_payload_ids(session, caplog):
    seed_user_dependents(session)
    with caplog.at_level(logging.DEBUG):
        for body in (
            user_created(),
            org_created(),
            member_added(),
            member_removed(),
            user_deleted(),
        ):
            dispatch(session, body)
    assert USER not in caplog.text
    assert ORG not in caplog.text
    assert "a@example.com" not in caplog.text


def test_conflict_with_different_event_is_retry_not_duplicate(session, monkeypatch):
    """A raced write by ANOTHER event must not be acked as a duplicate."""
    from sqlalchemy.exc import IntegrityError

    def raising(sess, event):
        raise IntegrityError("stmt", {}, Exception("ref_users pk"))

    out = dispatch(session, user_created(), {EventType.USER_CREATED: raising})
    assert out is Outcome.RETRY
    assert counts(session) == (0, 0)
