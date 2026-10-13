# FuzeFront -> FuzeKeys event and reference-data contract

Story: FKY-9 (design + scaffold). Machine-readable contract: [`data-contract.json`](../data-contract.json).
Schemas: `backend/app/events/schemas.py`. Consumer interface: `backend/app/events/consumer.py`.
Handlers: `backend/app/events/handlers.py` (FKY-10).

## Ownership

FuzeFront is the single writer of `user` and `org`. FuzeKeys stores *references*
(`usr_<uuid>`, `org_<uuid>`), bare, exactly as issued (reserved spine prefixes,
`scripts/gate_identifier.py`). FuzeKeys never writes to those entities.

| Reference | Validation | On delete |
|---|---|---|
| `user` | L1 (`warn`, promote to `enforce` once projection lag is in budget) | `cascade` (soft and hard) via `user.deleted` |
| `org` | L1 (`warn`) | `cascade` via `org.deleted` -- **open gap**, see below |

## Events (envelope v2)

`eventId`, `eventType`, `schemaVersion` (=2), `aggregateType`, `aggregateId`,
`aggregateVersion` (bumped on every change; the ordering key), `occurredAt`
(timezone-aware), `payload`.

| eventType | aggregate | payload |
|---|---|---|
| `user.created` | user | `userId` |
| `user.deleted` | user | `userId`, `deletionMode` (`soft`/`hard`, default `hard`) |
| `org.created` | org | `orgId`, `ownerUserId?` |
| `org.member.added` | org | `orgId`, `userId`, `role?` |
| `org.member.removed` | org | `orgId`, `userId` |

`aggregateId` must equal the payload's aggregate id. Unknown extra fields are
ignored and never persisted.

## Consumer semantics (`dispatch`)

- unknown `eventType` -> log metadata, ignore
- malformed envelope or schema-violating payload -> dead-letter (reason code, field
  locations, payload SHA-256; raw body is **not** stored), no state applied
- duplicate `eventId` -> no-op; `aggregateVersion` <= applied -> stale, skipped
- handler + inbox row + version bump are one savepoint: no partial state; failure -> `RETRY`

Tables (migration `e2026evt01`): `event_inbox`, `event_aggregate_versions`,
`event_dead_letters`, `event_outbox` (provisioned; nothing emitted yet).

## Transport decision

**Decision: FuzeFront-authenticated webhook to a REST ingress endpoint.**

Rationale:
- This repo has no Kafka client, broker config or topic; adding one means new
  infra, a new runtime dependency and a new failure mode for a four-entity
  reference feed.
- It already has the auth primitive: `app/security/fuzefront_auth.py`
  (`MachineTokenVerifier`). The ingress must accept only a verified
  `fuze-workload` token whose subject is FuzeFront's service identity and which
  carries an events scope. Do **not** reuse `delegated_auth` as-is: it requires a
  user delegation token, which a system event push does not have. FKY-10 adds a
  workload-only dependency and registers the route in `governance/auth-guards.txt`.
- At-least-once + retry is safe because the consumer is idempotent and
  version-guarded.

Ingress contract for FKY-10: `POST` envelope v2 JSON; body limit 64 KiB;
`200` for APPLIED/DUPLICATE/STALE/IGNORED_UNKNOWN_TYPE/UNHANDLED, `422` for
DEAD_LETTERED (do not retry a poison message), `503` for RETRY. The route and its
OpenAPI entry are **not** added in FKY-9.

Alternative: a Kafka consumer group on a FuzeFront-owned topic, if the platform
standardizes on Kafka. The broker and topic are then delegated to FuzeInfra via
`@claude`; nothing is built for it from this repo.

## Open items

1. `org.deleted` is not in the five-event scope, so the `org` on-delete policy
   cannot fire. FuzeFront should add it (or the policy must be re-decided).
2. `tenant`/`tenant_id` columns are assumed to hold the org id; verify in FKY-10.
3. Id format is validated structurally as `<prefix>_<uuid>`; replace with
   `fuzefront_identity.assert_ref` when that package is adopted.
4. `governance/data-contract.schema.json` (FuzeSDLC) was unreachable; re-validate
   `data-contract.json` against it.

## Handlers (FKY-10)

Handlers write FuzeKeys' local read-only reference index -- `ref_users`, `ref_orgs`,
`ref_org_members` (migration `e2026evt02`; bare ids, no PII, no cross-aggregate FKs).
They do not reuse the legacy local-auth `users`/`organizations` tables: those have
integer keys and NOT NULL credential columns an id-only event cannot populate.

`user.deleted` (soft and hard) applies the `cascade` policy: the `ref_users` row is kept
as a tombstone (`inactive` for soft, `deleted` for hard), `platform_identities` bindings
and `ref_org_members` rows are deleted, `connector_credentials` are set to
`owner_deleted` (leasing requires `connected`) with `identity_email` cleared, and
`connector_grant_intents` are set to `absent`.

**Residual (open item 5):** Vault secrets behind `owner_deleted` credentials are not
deleted inline -- Vault I/O cannot run inside the DB savepoint, and dropping `vault_ref`
would orphan the secret. A reconciler must purge Vault material for `owner_deleted` rows.
