"""Handlers for the five FuzeFront user/org events (FKY-10).

Contract (see ``data-contract.json`` and ``consumer.dispatch``):

* FuzeFront is the SINGLE WRITER of ``user``/``org``. These handlers only maintain
  FuzeKeys' local read-only reference index (``ref_users``, ``ref_orgs``,
  ``ref_org_members``) and apply the ``user`` on-delete policy to FuzeKeys' own
  rows. They never write anything back to FuzeFront.
* Handlers run INSIDE ``dispatch``'s savepoint together with the inbox row and
  the aggregate-version bump. They must not commit/rollback; any exception rolls
  the whole unit back and ``dispatch`` returns RETRY (no ack => redelivery).
* Idempotent: re-applying the same event, or one with a version not newer than the
  row's own ``source_version``, is a no-op (defence in depth behind the
  ``event_aggregate_versions`` guard in ``dispatch``).
* PII: only counts and event metadata are logged -- never ids from the payload.

User on-delete policy = ``cascade`` for BOTH deletion modes (data-contract
``references[user].onDelete``). The ``ref_users`` row itself is never hard
deleted: it becomes a tombstone (``deleted`` for hard, ``inactive`` for soft) so
later reference checks resolve to "deleted user" instead of "unknown user".
Dependent FuzeKeys rows keyed on the user's subject are revoked as follows:

* ``platform_identities``      deleted -- the subject->local user binding is the
                               access path, so access ends in this transaction.
* ``connector_credentials``    ``status`` -> ``owner_deleted`` and
                               ``identity_email`` cleared. Leasing requires
                               ``status == 'connected'``, so access ends now. The
                               row keeps ``vault_ref`` ON PURPOSE: the Vault secret
                               is external I/O that cannot run inside this DB
                               savepoint, and dropping the pointer would orphan it.
                               A reconciler purges Vault material for
                               ``owner_deleted`` rows (see docs/open items).
* ``connector_grant_intents``  ``desired_state`` -> ``absent`` (the existing
                               operator-reconciliation outbox).
* ``ref_org_members``          the user's memberships are removed.
"""

import logging
from datetime import datetime, timezone
from typing import Dict

from sqlalchemy import delete, update
from sqlalchemy.orm import Session

from app.events.schemas import (
    ConsumedEvent,
    DeletionMode,
    EventType,
    OrgCreatedPayload,
    OrgMemberAddedPayload,
    OrgMemberRemovedPayload,
    UserCreatedPayload,
    UserDeletedPayload,
)
from app.models.connector import ConnectorCredential, ConnectorGrantIntent
from app.models.fuzefront_refs import (
    USER_ACTIVE,
    USER_DELETED,
    USER_INACTIVE,
    RefOrg,
    RefOrgMember,
    RefUser,
)
from app.models.platform_identity import PlatformIdentity

logger = logging.getLogger(__name__)

OWNER_DELETED = "owner_deleted"
DEFAULT_MEMBER_ROLE = "member"


def _meta(event: ConsumedEvent, **counts: int) -> dict:
    return {
        "event_id": event.event_id,
        "event_type": event.event_type.value,
        "aggregate_version": event.aggregate_version,
        **counts,
    }


def handle_user_created(session: Session, event: ConsumedEvent) -> None:
    payload = event.payload
    assert isinstance(payload, UserCreatedPayload)
    row = session.get(RefUser, payload.user_id)
    if row is None:
        session.add(
            RefUser(
                user_id=payload.user_id,
                status=USER_ACTIVE,
                source_version=event.aggregate_version,
            )
        )
        return
    if event.aggregate_version <= row.source_version:  # type: ignore[operator]
        return  # idempotent / stale at row level
    row.status = USER_ACTIVE  # type: ignore[assignment]
    row.deletion_mode = None  # type: ignore[assignment]
    row.deleted_at = None  # type: ignore[assignment]
    row.source_version = event.aggregate_version  # type: ignore[assignment]


def _cascade_user_delete(session: Session, user_id: str) -> Dict[str, int]:
    """Apply the ``cascade`` on-delete policy to FuzeKeys' rows for this user."""
    counts = {
        "platform_identities": session.execute(
            delete(PlatformIdentity).where(PlatformIdentity.subject == user_id)
        ).rowcount,
        "connector_credentials": session.execute(
            update(ConnectorCredential)
            .where(
                ConnectorCredential.owner_subject == user_id,
                ConnectorCredential.status != OWNER_DELETED,
            )
            .values(status=OWNER_DELETED, identity_email=None)
        ).rowcount,
        "connector_grant_intents": session.execute(
            update(ConnectorGrantIntent)
            .where(
                ConnectorGrantIntent.owner_subject == user_id,
                ConnectorGrantIntent.desired_state != "absent",
            )
            .values(desired_state="absent")
        ).rowcount,
        "org_memberships": session.execute(
            delete(RefOrgMember).where(RefOrgMember.user_id == user_id)
        ).rowcount,
    }
    return counts


def handle_user_deleted(session: Session, event: ConsumedEvent) -> None:
    payload = event.payload
    assert isinstance(payload, UserDeletedPayload)
    soft = payload.deletion_mode is DeletionMode.SOFT
    status = USER_INACTIVE if soft else USER_DELETED
    row = session.get(RefUser, payload.user_id)
    if row is None:
        # Delete observed before (or without) the create: record the tombstone so
        # a later reference check resolves to "deleted", not "unknown".
        session.add(
            RefUser(
                user_id=payload.user_id,
                status=status,
                deletion_mode=payload.deletion_mode.value,
                deleted_at=datetime.now(timezone.utc),
                source_version=event.aggregate_version,
            )
        )
    elif event.aggregate_version > row.source_version:  # type: ignore[operator]
        row.status = status  # type: ignore[assignment]
        row.deletion_mode = payload.deletion_mode.value  # type: ignore[assignment]
        row.deleted_at = datetime.now(timezone.utc)  # type: ignore[assignment]
        row.source_version = event.aggregate_version  # type: ignore[assignment]
    else:
        return  # idempotent / stale at row level: cascade already applied
    counts = _cascade_user_delete(session, payload.user_id)
    logger.info("user on-delete cascade applied", extra=_meta(event, **counts))


def handle_org_created(session: Session, event: ConsumedEvent) -> None:
    payload = event.payload
    assert isinstance(payload, OrgCreatedPayload)
    row = session.get(RefOrg, payload.org_id)
    if row is None:
        session.add(
            RefOrg(
                org_id=payload.org_id,
                owner_user_id=payload.owner_user_id,
                source_version=event.aggregate_version,
            )
        )
        return
    if event.aggregate_version <= row.source_version:  # type: ignore[operator]
        return
    row.owner_user_id = payload.owner_user_id  # type: ignore[assignment]
    row.source_version = event.aggregate_version  # type: ignore[assignment]


def handle_org_member_added(session: Session, event: ConsumedEvent) -> None:
    payload = event.payload
    assert isinstance(payload, OrgMemberAddedPayload)
    user = session.get(RefUser, payload.user_id)
    if user is not None and user.status != USER_ACTIVE:
        # Never (re)grant membership to a deleted/inactive user.
        logger.info("member add skipped: user not active", extra=_meta(event))
        return
    role = payload.role or DEFAULT_MEMBER_ROLE
    row = session.get(RefOrgMember, (payload.org_id, payload.user_id))
    if row is None:
        session.add(
            RefOrgMember(
                org_id=payload.org_id,
                user_id=payload.user_id,
                role=role,
                source_version=event.aggregate_version,
            )
        )
        return
    if event.aggregate_version <= row.source_version:  # type: ignore[operator]
        return
    row.role = role  # type: ignore[assignment]
    row.source_version = event.aggregate_version  # type: ignore[assignment]


def handle_org_member_removed(session: Session, event: ConsumedEvent) -> None:
    payload = event.payload
    assert isinstance(payload, OrgMemberRemovedPayload)
    row = session.get(RefOrgMember, (payload.org_id, payload.user_id))
    if row is None:
        return  # already removed / never added: idempotent
    if event.aggregate_version <= row.source_version:  # type: ignore[operator]
        return
    session.delete(row)


FUZEFRONT_HANDLERS = {
    EventType.USER_CREATED: handle_user_created,
    EventType.USER_DELETED: handle_user_deleted,
    EventType.ORG_CREATED: handle_org_created,
    EventType.ORG_MEMBER_ADDED: handle_org_member_added,
    EventType.ORG_MEMBER_REMOVED: handle_org_member_removed,
}
