# Vault sharing: vault types, move / copy / share

- Ticket: FKY-12 (design spike) for FKY-3
- Status: Proposed, pending security review (see decision record)
- Decision: [FKY-12-vault-sharing-decision-record.md](../decisions/FKY-12-vault-sharing-decision-record.md)
- Frozen contract: [vault-sharing.v1.yaml](../contracts/vault-sharing.v1.yaml)
- This is a design only. No executable code, no migration files, no policy file edits.

## 1. Scope, non-goals, assumptions

In scope: a first-class **Vault** entity (personal / org / org-user), **share** (user,
persona, org, org-user group), **move**, **copy**, **revoke**, **list shared / shared with
me**, and how each maps onto the Permit `VaultAsset` resource and the broker.

Non-goals (v1): re-sharing by a sharee; sharing a persona's PII profile (`Identity`
columns) - personas are *grantees*, assets are what is shared; cross-tenant sharing;
offboarding/transfer of a deleted user's personal vault; syncing a copy with its source;
agent-initiated share/move/copy.

Assumptions (the reviewer should confirm; each is cheap to remap if wrong):

- **A1. "org-user" vault** = a vault owned by an org and scoped to a named **org group**
  (a subset of that org's members). The task wording "org-user group expansion to
  members" implies a group. If it instead means "a user's slice inside an org", the
  `org_groups` tables collapse to one owner user and the rest of the design is unchanged.
- **A2.** Custody stays split exactly as today: Vaultwarden holds Login and Card items,
  OpenBao KV v2 holds API credentials; Postgres holds only metadata and opaque handles
  (`accounts.vault_item_ref`, `identity_cards.vault_item_ref`,
  `api_credentials.openbao_path`).
- **A3.** Integer primary keys everywhere, matching the existing API (`/identities/{id}`).
  Object-level authorization, not id obscurity, is the protection.

## 2. Current state (verified in code)

| Area | Fact | File |
|---|---|---|
| Ownership | A persona (`Identity`) has one `user_id`. Assets hang off the persona (`identity_id` NOT NULL on `accounts`, `identity_cards`, `api_credentials`). No vault entity exists. | `models/identity.py`, `account.py`, `vault_assets.py` |
| Tenancy | `Identity.org_id` (nullable) tags a persona with an org; `Identity.vault_collection_ref` is the persona's Vaultwarden collection. `organization_members.role` is owner/admin/member. | `models/identity.py`, `organization.py` |
| Values | Never in Postgres for vault assets: Vaultwarden item id / OpenBao path only. Legacy `encrypted_*` columns remain on `accounts`. | `vault_assets.py`, `account.py` |
| Broker | Grants are bound to a transport principal, TTL-clamped, single-use by default; redeem returns a derived (HMAC) credential or an operation token; revoke is grantor-only; high sensitivity needs human approval. | `broker/service.py`, `derived.py`, `grant.py` |
| Custody seam | `SecretResolver.load_root`; `MutableSecretVault.put/delete`; implementations: `InMemoryVault`, `OpenBaoKV2Vault`. No Vaultwarden adapter and no copy/move primitive. | `broker/vault.py` |
| Authz | Two-layer pattern: select the row by SQL ownership, then `require_owner_permission` -> Permit instance decision keyed `<type>:<id>`; fail closed (403/503); needs a verified `PlatformIdentity`. | `security/owner_authz.py`, `platform_authz.py` |
| Policy | `VaultAsset` actions read / reveal / create / update / delete; one instance role `owner`; tenant roles viewer (read), operator (read, create, update), admin (adds reveal, delete). `reveal` is deliberately admin-only: operators write but cannot read back. | `registration/policy.json`, `registration/README.md` |
| Sensitivity | Per the identity-vault spec: logins medium; cards and API tokens high (human approval before release). | `docs/superpowers/specs/2026-06-24-identity-vault-mcp-design.md` section 7 |
| Alembic head | `d2026sms01` (chain: ... `e4a1f0b21c01` -> `f5b2c0d34e12` -> `a2026gmail01` -> `b2026link01` -> `c2026conn01` -> `d2026sms01`). | `backend/alembic/versions/` |

## 3. Architecture in one picture

```
 caller (human session | delegated user | agent token)
        |
        v
  /api/v1/vaults, /vault-shares, /vault-assets/{move,copy}      <- this contract (metadata only)
        |
        |  1. authenticate (token kind, verified PlatformIdentity)
        |  2. select row; resolve effective_role from ACL   (vaults + vault_shares + memberships)
        |  3. Permit instance decision (fuzekeys_VaultAsset, action, resource_key)   fail closed
        v
   ACL decides WHETHER                      custody adapter moves values
        |                                   (in-process only, never via the API)
        |  on ACCESS (use):
        v
   BrokerService.grant(system grantor -> consumer principal, <=60s, single use)  + redeem
        |                                   (approval gate for sensitivity=high stays in the broker)
        v
   short-lived derived credential / operation token to the consumer
```

ACL = durable entitlement. Broker = ephemeral release. They meet at one in-process call.

## 4. The Vault entity

### 4.1 Types

| Type | Owner principal | Who has implicit authority | Typical content |
|---|---|---|---|
| `personal` | one user (`owner_user_id`) | that user is `owner` | the user's personas' logins, cards, API credentials |
| `org` | an organization (`org_id`) | org `owner` and `admin` members are `owner` of the vault; org `member`s have nothing unless shared | company-wide shared credentials |
| `org_user` | an org group (`owner_group_id`, belongs to `org_id`) | org owner/admin are `owner`; each group member holds their `org_group_members.role` (viewer / operator / admin) | team credentials |

Exactly one personal vault per user. `org` and `org_user` vaults are created explicitly
(`POST /api/v1/vaults`); personal vaults are implicit.

### 4.2 Tables (sketch, columns only)

`vaults`
- `vault_id` PK; `type` (`personal|org|org_user`, string + CHECK, matching the repo's
  string-status convention rather than a Postgres enum); `name`; `status`
  (`active|archived`); `org_id` FK nullable; `owner_user_id` FK nullable;
  `owner_group_id` FK nullable; `created_by_user_id`; `created_at`; `updated_at`.
- Custody: `custody_mode` (`legacy_persona_collections|native`), `vw_collection_ref`
  nullable, `bao_path_prefix` nullable. **Server-side only, never in any response.**
- CHECK per type: personal => `owner_user_id` set, `org_id` and `owner_group_id` null;
  org => `org_id` set, owner columns null; org_user => `org_id` and `owner_group_id` set.
- Unique: one active personal vault per `owner_user_id`; `(org_id, type, name)` unique.

`org_groups` (`id`, `org_id`, `name`, unique `(org_id, name)`) and `org_group_members`
(`group_id`, `user_id`, `role` viewer|operator|admin, unique `(group_id, user_id)`).
Removing a user from `organization_members` removes their group memberships in the same
transaction.

Asset tables (`accounts`, `identity_cards`, `api_credentials`), additive:
- `vault_id` FK (nullable during rollout, NOT NULL after backfill verification).
- `identity_id` becomes **nullable** (a detached asset has no persona).
- `custody_state` (`ready|moving|needs_recovery`, default `ready`).
- `copied_from_kind`, `copied_from_id` (provenance only; deliberately **no FK** so lineage
  survives deletion of the source).
- `Identity.vault_id` nullable: the home vault of the persona's PII profile. PII profile
  sharing is a non-goal; this only records where it lives.

Asset sensitivity is derived from kind (login medium, card high, api_credential high),
not stored.

### 4.3 Relation to `Identity.org_id` and existing assets

- `Identity.org_id` keeps its meaning: the persona's **tenant tag**. It is not a vault
  and does not move anything. Backfill puts every existing persona and asset in the
  owner's **personal** vault, including org-tagged personas (the existing spec says
  personas are private to the owning user; backfill must not silently widen access).
- **Tenant boundary rule** (422 `tenant_boundary_violation`): an `org`/`org_user` vault of
  org O may only receive assets whose owning user is currently a member of O, and a
  retained persona must have `org_id` equal to O or null. Otherwise the persona is
  detached (or `target_persona_id` must be supplied and in scope).
- A moved/copied asset keeps its persona only when the target vault is owned by the same
  user and tenant; otherwise `persona_id` becomes null. This prevents leaking persona
  linkage (a persona name/identity relationship) to org members.
- Logins are `Account` rows. Sharing a login grants `VaultAsset` actions on a
  `login:<id>` instance; it **never** grants `Account:*` (no lifecycle, signup or
  automation rights over the account).

## 5. ACL data model

`vault_shares`
- `share_id` PK; `resource_kind` (`vault|asset`); `vault_id` FK (always set; for an
  asset share it is the asset's vault at share time, for indexing); `asset_kind` and
  `asset_id` (null for vault shares; polymorphic, so integrity is enforced by the service
  and by the move/delete hooks, not by an FK).
- `grantee_type` (`user|persona|org|org_group`), `grantee_id`.
- `role` (`viewer|operator|admin`), `state`
  (`pending_activation|active|revoked|expired`), `expires_at` nullable,
  `created_by_user_id`, `created_at`, `updated_at`, `revoked_at`, `revoked_reason`
  (`manual|moved|asset_deleted|vault_archived|grantee_left|expired`),
  `permit_synced_at`.
- Unique partial index on (resource, grantee) where state is pending_activation or
  active. Indexes: `(grantee_type, grantee_id, state)` for "shared with me";
  `(vault_id, state)` and `(asset_kind, asset_id, state)` for "granted".
- Cap: 100 active shares per resource (422 `share_limit_reached`).

`vault_share_grant_intents` (outbox, mirrors `connector_grant_intents`): `share_id`, `op`
(`grant|update|revoke`), desired role, resource key, status, attempts, sanitized
`last_error` (no PII). Also written on group/org membership change so Permit assignments
follow membership. Written in the same transaction as the share row (transactional outbox,
per the data-consistency standard).

`vault_operations` and `vault_operation_items` (idempotency and saga journal):
`operation_id`, actor, `sha256(Idempotency-Key)`, `sha256(request)`, kind, status,
metadata-only response snapshot; per item: step, status, source/target custody markers
(opaque handles, server-side only). Unique `(actor, key_hash)`. Retained 24h, except
items in `needs_recovery`, which are retained until resolved.

Broker, additive: nullable indexed `broker_grants.vault_share_id` so revoking a share can
revoke the leases issued under it.

## 6. Authorization mapping

### 6.1 Principals and callers

| Caller | Read routes (vaults, received) | Mutating routes (share, patch, revoke, move, copy, create vault) |
|---|---|---|
| Human session (JWT) with verified `PlatformIdentity` | yes | yes |
| Delegated end-user (service + `X-Fuze-Delegation`), subject and tenant matching the binding | yes | yes |
| Agent token | metadata only, and only shares reaching its scoped personas | **no** - 403 `human_session_required` |

Rationale (endpoint-authorization, BOPLA and exfiltration): an LLM agent must not be able to
widen who can read a secret. The actor is always the verified token subject; no body field
names the actor.

### 6.2 Role to action matrix

Share roles reuse the Permit `VaultAsset` role names but as **resource-instance roles**.
The tenant-level roles in `registration/policy.json` are unchanged.

| Action | viewer | operator | admin | owner (vault authority) |
|---|:--:|:--:|:--:|:--:|
| `read` (metadata) | x | x | x | x |
| `use` (broker-issued short-lived credential, no raw value) | x | x | x | x |
| `create` (add assets to the vault) |  | x | x | x |
| `update` (rotate/replace a value, write-only) |  | x | x | x |
| `reveal` (raw value to a human) |  |  | x | x |
| `delete` |  |  | x | x |
| `share` (create/patch/revoke shares) |  |  |  | x |

This preserves the existing invariant that `reveal` is admin-only and that an operator can
write without reading back. `share` is owner-only, so a share role of `admin` cannot
re-share (no re-share in v1; keeps revocation free of cascades).

Grantee caps (422 `role_not_allowed_for_grantee`): `persona` and `org` grantees are capped
at `operator` (so `reveal` is unreachable through a persona or a whole-org grant);
`user` and `org_group` may be `admin`.

Grantee-by-resource matrix (422 `grantee_type_not_allowed_for_resource`):

| Resource in a ... vault | user | persona | org | org_group |
|---|:--:|:--:|:--:|:--:|
| personal | x | x |  |  |
| org | x | x | x (same org) | x (same org) |
| org_user | x | x |  | x (same org) |

To give a team access to a personal asset, *copy* it into an `org_user` vault. This keeps
"who is in the audience" decidable from the vault, not from scattered shares.

**Persona grantee semantics.** A share to a persona is usable only by principals acting
as that persona: an agent token whose `agent_scopes` include `identity:<id>`. The
persona's owning human is not implicitly included. This lets a user extend one agent's
reach to an asset in another vault without sharing it with another human.

### 6.3 Policy delta (proposed, NOT applied in this spike)

Changes FKY-3 must make to `registration/policy.json` and the Helm registration copy
(`docs/security/owner-grant-inventory.md` requires them to match):

1. Add VaultAsset actions `use` and `share`.
2. Add VaultAsset instance roles `viewer`, `operator`, `admin` per the matrix above;
   extend `owner` with `use` and `share`.
3. Tenant roles untouched. A tenant `admin` still has `VaultAsset:reveal` tenant-wide in
   Permit, so **Permit alone is never sufficient**: the local ACL decision is a
   necessary condition (AND), exactly as `owner_authz.py` already requires the SQL row
   selection first.
4. Resource keys: `vault:<id>` for vault-level shares/ownership; `login:<id>`,
   `card:<id>`, `api-credential:<id>` for asset-level (the last matches the existing
   inventory key). Add the new routes to `docs/security/mounted-route-authorization.json`
   with `instance_enforced` assessments (it is checked by
   `test_mounted_authorization_inventory.py`).

### 6.4 Decision procedure (every access and every mutation)

1. Verify token kind and the `PlatformIdentity` binding (403 `platform_identity_required`).
2. Select the target row (asset or vault) and compute `effective_role`:
   - vault authority: personal owner; org owner/admin; group member role;
   - plus every active, unexpired share whose resource is the asset or its **current**
     vault and whose grantee matches (user id; persona in scope; org membership;
     group membership evaluated **live**);
   - take the maximum (`viewer < operator < admin < owner`). Multiple paths never reduce.
3. No `read` => 404 (absent and invisible are identical). Has `read` but lacks the
   action => 403 `insufficient_role`.
4. Permit instance decision for the path that produced the maximum role; anything other
   than an explicit allow => 403; decision service unreachable => 503
   `authorization_unavailable`. Never allow on error.
5. Mutations: re-check under a row lock; write audit; commit.

**Share activation is eventually consistent, revocation is not.** A new share is
`pending_activation` and grants nothing until the outbox reconciler has provisioned the
Permit instance grant (the runtime does not apply grants itself today - see
`ConnectorGrantIntent`). Revoke/downgrade is effective at once because the local ACL
is evaluated before Permit. Open question Q3 asks whether the backend workload may
apply instance grants directly, which would make activation synchronous without changing
this contract (`state` already allows both).

## 7. Access path: how the broker issues the credential

Not part of the frozen contract (it is the existing use/reveal surface made ACL-aware),
recorded here because it is the reason the broker stays in the design.

For `use` by a consumer (agent, service or user session):

1. ACL + Permit allow `use` (section 6.4).
2. Vault service calls `BrokerService.grant` with: grantor = a fixed system transport
   principal (`platform:fuzekeys-vault`), `redeemer_identity` = the consumer's already
   verified principal string, `secret_ref` = the asset's current custody handle, `scope`
   = {vault, asset key, role, share id}, TTL at most 60 s, `single_use=True`, sensitivity
   by kind. Then `redeem` in-process with the consumer's authenticated
   `TransportContext`. (FKY-3 adds a thin `lease()` wrapper; no HTTP loopback.)
3. Everything the broker already enforces still applies: binding, expiry, single use,
   revocation, non-disclosing denial, and the **human approval gate for `high`**
   (cards and API credentials), surfaced as `approval_required`.
4. `broker_grants.vault_share_id` links the lease to the share; revocation sweeps by it.
   Because leases live at most 60 s, a missed sweep is bounded.

The consumer principal string for platform subjects is `platform:<tenant>:<subject>`.
`TransportIdentity.method` is a free-form string, so a `platform-session` method needs no
broker schema change.

**Reveal is different, and is open question Q2.** `derive_credential` is a one-way HMAC
(`fkderiv_...`): downstream services validate it by re-deriving with the root. It is not
a way to show a human their password. Raw reveal for a human therefore cannot be a broker
derived credential. It stays on the existing custody reveal path (as in
`routers/credentials.py`), now gated by `reveal` on the ACL + Permit. If the reviewer
wants it to flow through the broker, that needs a new release kind that deliberately
relaxes "the root never leaves the vault" for the human channel and must be a separate,
explicit security decision.

## 8. Move vs copy

### 8.1 Comparison

| | MOVE | COPY |
|---|---|---|
| Custody | **Re-home.** One custody record, relocated. Asset row id is stable; the custody handle may change (OpenBao: write new path, verify, delete old; Vaultwarden same-org: change collection membership of the item). | **Duplicate.** A second, independent custody record with a **new** handle and a **new** asset row id. |
| Source afterwards | gone from source vault | untouched |
| Shares | Asset-scoped shares revoked with reason `moved`; source vault-level shares stop applying (they key off the asset's current vault); target vault's access applies. Leases issued under revoked shares are revoked. | None inherited. Source shares unchanged. Target vault's access applies. |
| Lineage | audit entry; same asset id | `copied_from_kind/id` on the new row (provenance only; no sync) |
| Persona | kept only if same owner and tenant, else detached; or `target_persona_id` | same |
| Source rights required | `delete` | `reveal` |
| Target rights required | `create` on target vault | `create` on target vault |
| Why those rights | removes it from the source audience | the server reads the value on the caller's behalf and writes it where a different audience may read it, so it needs the strongest read right |
| High sensitivity (card, API credential) crossing a vault-type or owner boundary | human approval (202 / item `approval_required`) | same |

Revocation never recalls a copy: anyone who held `reveal` and copied the value retains
that copy. This is a documented property, mitigated by `reveal` being admin-only, by the
`reveal` requirement for copy, and by the approval gate for high sensitivity.

### 8.2 Move sequence (per item; items are independent)

1. Authorize (section 6.4): `delete` on source, `create` on target vault, tenant rule.
2. Under a row lock set `custody_state=moving` and journal the step in
   `vault_operation_items` (idempotent by operation id). Concurrent writers get 409
   `asset_in_transition`.
3. High sensitivity and boundary crossing => create approval, return `approval_required`
   for the item; resume on retry after approval.
4. Custody step via the adapter (value stays in-process; never serialized, logged or
   returned). Verify by handle existence/hash comparison, not by returning the value.
5. One DB transaction: set `vault_id` (and persona rule), update custody handle, revoke
   asset-scoped shares (`moved`), mark leases for sweep, write audit, outbox
   `revoke` intents, `custody_state=ready`.
6. Delete the old custody record last (OpenBao old path). If this fails, the asset is
   already consistent; a janitor retries (orphan handle only, no exposure).

### 8.3 Copy sequence (per item)

Same as move through step 4, but: read source in-process, write target (new handle), then
in one DB transaction insert the new asset row (`vault_id`, lineage, `custody_state=ready`)
and audit. Source row is never locked beyond the read. If the DB insert fails after the
custody write, the journal entry drives deletion of the orphan target record on retry or
by the recovery job.

### 8.4 Atomicity and partial failure

Custody (Vaultwarden/OpenBao) and Postgres cannot share a transaction, so the unit of
consistency is the **item**, driven by the journal:

- An item is always fully in source, fully in target, or `moving`/`needs_recovery`
  (frozen for writers, still readable by existing rights only if its custody handle
  resolves; otherwise reads fail closed). Never half-visible in both vaults.
- A batch (up to 50 items) is **not** atomic across items. Aggregate status is 200 if
  all completed, 202 if all waiting for approval, else 207 with per-item results.
- Request-level problems (target vault missing/invisible, caller cannot `create` there,
  bad body, missing Idempotency-Key) fail the whole request with a 4xx **before** any
  item is touched.
- Retrying the same request with the same `Idempotency-Key` resumes unfinished items
  and is a no-op for completed ones. Same key with a different body is 409.

### 8.5 Custody adapter gap

`MutableSecretVault` offers `put/load_root/delete` only. FKY-3 needs a custody protocol
with `copy(src_handle, dst_prefix) -> dst_handle` and `rehome(src_handle, dst_prefix)
-> handle`, implemented for OpenBao KV v2 (read+write+delete) and for Vaultwarden
(collection membership change within the single org silo, copy via create). No
Vaultwarden adapter exists in the repo today (Q6).

## 9. Share semantics

- **Scope**: a whole vault (all current and future assets in it) or one asset.
- **Group/org grantee**: one row, expanded to members **live** at each access. Adding a
  member grants access on the next request; removing a member (from the group or from the
  org) removes it on the next request, with no per-member rows to clean up. Permit
  assignments are reconciled from membership-change events through the same outbox; the
  local live check makes removal immediate regardless of reconciler lag.
- **Multiple paths**: effective role is the maximum across direct, persona, org and
  group shares plus vault authority. Revoking one path leaves the others.
- **Expiry**: `expires_at` is checked on every access (not only by a reaper); the reaper
  merely sets `state=expired`.
- **Visibility**: `received` lists only shares that currently give the caller access
  (active, unexpired, caller still in the group/org). It never lists revoked, expired or
  pending shares and never exposes custody handles or values.
- **Who can revoke**: anyone with `share` on the resource (vault authority), regardless of
  who created the share; plus the grantee of a **direct user** share ("leave").

## 10. Edge cases

| # | Scenario | Behaviour | Status / code |
|---|---|---|---|
| E1 | **Self-share**: grantee resolves to the caller, or to the user who already has `owner` authority on the resource | Rejected, no row written | 409 `self_share` |
| E1b | Share an asset to a **persona the caller owns** (extend own agent's reach) | Allowed, role capped at operator | 201 |
| E2 | Duplicate share, same resource, grantee and role | Idempotent, returns existing | 200 |
| E3 | Same resource and grantee, different role | Use PATCH | 409 `share_exists` |
| E4 | Revoke **after move** of an asset-scoped share | Share was auto-revoked at move time (`revoked_reason=moved`); DELETE returns the revoked share | 200 (idempotent) |
| E5 | Revoke of a **source-vault-level** share after an asset moved out | Share never reached the moved asset after the move (it keys off current vault); revoking affects only assets still in that vault | 200 |
| E6 | Revoke races a move of the same asset | Both take the asset row lock; serialized. Either order ends with no access via the old share | 200 / item `completed` |
| E7 | Revoke **after copy** | Copy is independent and inherited nothing; revoking the source share does not touch the copy. A grantee who already copied keeps the copy | 200 |
| E8 | **Org-user group expansion** | One share row to the group; members resolved live; later joiners get access, leavers lose it on next request; empty group is allowed and grants nothing | 201 |
| E9 | Org grantee: sharer not a member of that org | Org is "not found" for them | 404 `grantee_not_found` |
| E10 | Member with no verified `PlatformIdentity` in an expanded group | Cannot be evaluated by Permit: denied (fail closed), omitted from their `received` | n/a (deny) |
| E11 | User holds viewer directly and admin via group | Effective admin; revoking the group share leaves viewer | n/a |
| E12 | Share/move/copy of an asset in `custody_state != ready` | Frozen until recovery | 409 `asset_in_transition` |
| E13 | Asset deleted while shared | Its shares are revoked (`asset_deleted`) in the delete transaction | n/a |
| E14 | Vault delete / archive | Vault must be empty, else refused; archiving revokes vault shares (`vault_archived`); personal vault cannot be archived | 409 / n/a |
| E15 | Move or copy to the **same vault** | No new custody boundary; rejected | 409 `same_vault` |
| E16 | Share `expires_at` in the past or beyond 365 days | Rejected | 422 `invalid_expiry` |
| E17 | Share to `org` grantee with role `admin` | Rejected (cap) | 422 `role_not_allowed_for_grantee` |
| E18 | Share personal asset to org / org_group | Rejected; copy to an org_user vault instead | 422 `grantee_type_not_allowed_for_resource` |
| E19 | Group member tries to "leave" an org/group share individually | Not allowed | 403 `group_share_cannot_be_left` |
| E20 | Org owner removes a member who created shares | Shares remain (owned by the resource, not the creator); creator id is audit only | n/a |
| E21 | Persona grantee used by a human session of the persona's owner | Not honoured; only the scoped agent acts as the persona | n/a (deny) |
| E22 | Replay of a share/move/copy with the same Idempotency-Key and body | Original result returned | original status |
| E23 | Same Idempotency-Key, different body | Rejected | 409 `idempotency_conflict` |
| E24 | Move of a high-sensitivity asset across a vault-type or owner boundary | Human approval first | 202 / item `approval_required` |

## 11. Error cases

Global rule: 404 for absent-or-invisible, 403 only for visible-but-forbidden (contract R3);
error `detail` is fixed per code and never echoes names or foreign ids (R4); no response or
log ever carries a value (R1).

| # | Case | Status | Code | Notes |
|---|---|---|---|---|
| X1 | No/invalid/expired token | 401 | `unauthenticated` | |
| X2 | Agent token on a mutating route | 403 | `human_session_required` | Checked before any lookup |
| X3 | No verified `PlatformIdentity` binding | 403 | `platform_identity_required` | Same as `owner_authz.py` |
| X4 | **Unauthorized share**: caller can see the resource but lacks `share` (e.g. viewer/operator/admin sharee) | 403 | `insufficient_role` | |
| X5 | Unauthorized share: caller cannot see the resource | 404 | `resource_not_found` | Indistinguishable from nonexistent |
| X6 | Grantee does not exist, is in another tenant, or has no verified binding | 404 | `grantee_not_found` | One response for all three; no user-existence oracle |
| X7 | **Target vault missing** or not visible to the caller | 404 | `target_vault_not_found` | Request fails before any item is touched |
| X8 | Target vault visible but caller lacks `create` | 403 | `insufficient_role` | |
| X9 | Source item missing/invisible (move/copy) | item `failed` in 207 | `resource_not_found` | Other items continue |
| X10 | Source item visible but caller lacks `delete` (move) / `reveal` (copy) | item `failed` in 207 | `insufficient_role` | |
| X11 | **Partial move**: custody step done but DB commit failed, or a mid-batch failure | 207, item `needs_recovery` or `failed` | `custody_unavailable` / `internal_error` | Source never loses its value before the new location is verified; retry with the same key resumes |
| X12 | All items fail at item level | 207 | per item | Clients read `results[]` |
| X13 | Custody backend down | 503 | `custody_unavailable` | |
| X14 | Permit/Security decision service down or ambiguous | 503 | `authorization_unavailable` | Never an allow |
| X15 | Missing or malformed `Idempotency-Key` | 400 | `idempotency_key_required` | |
| X16 | Body validation (unknown field, bad type, `items` empty or >50, duplicate items) | 422 | `validation_error` | `additionalProperties: false` everywhere |
| X17 | Cross-tenant or persona/org mismatch on move/copy | 422 | `tenant_boundary_violation` | Item-level when only some items violate |
| X18 | Share limit per resource exceeded | 422 | `share_limit_reached` | |
| X19 | PATCH/DELETE on unknown or unmanageable share | 404 | `share_not_found` | |
| X20 | PATCH on revoked/expired share | 409 | `share_not_active` | |
| X21 | Rate limit on share/transfer mutations | 429 | `rate_limited` | `Retry-After` |
| X22 | Vault name already used in scope | 409 | `vault_name_conflict` | |

**Non-leakage of secret values.** Secrets are never in any request or response of this
contract. Moves and copies are "do this to assets named by id" operations; the response
reports ids, statuses and counts only. `AssetSummary.label` is a non-secret display string
(website name; card brand and last4; service and name). Custody handles
(`vault_item_ref`, `openbao_path`, `vault_ref`, collection ids) are never returned.
`additionalProperties: false` on every schema plus the banned-property-name list in the
contract make this machine-checkable. Audit rows carry ids and decisions only; request
bodies of these routes are not logged (logging standard: redaction on).

## 12. Migration sketch (not code)

All Alembic steps follow the repo rule: schema via Alembic only (`alembic upgrade head`),
expand-only, SQLite and PostgreSQL compatible (string+CHECK instead of DB enums, partial
indexes both support). New revisions chain after `d2026sms01`.

1. **Expand (schema, additive and nullable)**: create `vaults`, `org_groups`,
   `org_group_members`, `vault_shares`, `vault_share_grant_intents`, `vault_operations`,
   `vault_operation_items`; add `vault_id`, `custody_state`, `copied_from_*` to the three
   asset tables and `vault_id` to `identities`; relax `identity_id` to nullable on the
   three asset tables; add nullable `broker_grants.vault_share_id`.
2. **Backfill (idempotent job, batched per user, no custody I/O)**: for each user with
   identities create the personal vault (`custody_mode=legacy_persona_collections`,
   no collection/prefix); set `identities.vault_id` and each asset's `vault_id` from its
   persona. Org-tagged personas are backfilled to the owner's personal vault, not to an
   org vault. Org and org_user vaults are never auto-created. No Vaultwarden or OpenBao
   data is touched, so the backfill cannot lose or expose a secret.
3. **Verify**: query must show zero assets with NULL `vault_id`, one personal vault per
   such user, and CHECK constraints satisfied.
4. **Contract/enforce**: set `vault_id` NOT NULL on assets; add FKs and the partial unique
   indexes; add CHECK constraints.
5. **Switch read/write paths behind the flag** `fuzekeys.vault.sharing` (default OFF per
   the feature-flags standard; test both states). With the flag off, behaviour is exactly
   today's owner-only path; the additive schema is inert.
6. **Custody normalization is lazy**: the first cross-vault operation touching a
   `legacy_persona_collections` vault uses copy-style custody (put new, verify, delete
   old) rather than in-place re-home. No bulk re-collection of existing Vaultwarden items.

Rollback: turn the flag off; downgrade drops only the new tables/columns (share data is
lost; asset and custody data are not modified by any expand step). No destructive step
exists in this epic.

Deploy note for FKY-3: every PR that touches `backend/`, `frontend/` or `pii-tokenizer/`
must bump `Chart.appVersion` (release-version gate), and a human merges in a deploy
window. This spike changes only `docs/`, so it does not bump.

## 13. Audit

Reuse `audit_log` (no value columns). Proposed `decision` values (40-char limit):
`vault_created`, `share_created`, `share_updated`, `share_revoked`, `asset_moved`,
`asset_copied`, `transfer_approval_req`, `share_access_denied`. `resource_ref` carries
ids, e.g. `vault-share:12 vault:3 grantee=user:44 role=viewer`; never emails, names or
handles. Set `on_behalf_user_id` to the acting user (the broker's own `_audit` currently
leaves actor columns null; the new code should fill them). Denials on the ACL path are
audited with the same generic reason the client sees.

## 14. Follow-on stories to create under FKY-3 (spike deliverable, not created here)

| # | Story | Owner role | Depends on |
|---|---|---|---|
| 1 | Contract PR: land this contract, generate typed client, Prism mock (api-contract-first) | backend | this spike approved |
| 2 | DB: expand migration + idempotent backfill + verify + enforce | database-engineer | 1 |
| 3 | Vault and org-group services, `/vaults` routes | backend | 2 |
| 4 | ACL engine (`effective_role`), policy delta, outbox reconciler, route inventory entries | backend + security | 2, Q3 |
| 5 | Shares routes: create, list received/granted, patch, revoke | backend | 4 |
| 6 | Custody protocol (`copy`, `rehome`) for OpenBao KV2 and Vaultwarden | backend | Q6 |
| 7 | Move/copy routes, journal, saga recovery, approval integration | backend | 4, 6, Q5 |
| 8 | Broker `lease()` wrapper, `vault_share_id` link, revocation sweep | backend | 4 |
| 9 | Frontend: shared-with-me, share dialog, move/copy UI, built against the mock and frames | frontend | 1 |
| 10 | Independent authz and non-leakage test suite (BOLA matrix below) | test-engineer | 5, 7 |
| 11 | Flag `fuzekeys.vault.sharing` rollout and appVersion bumps per PR | devops | all |

BOLA/regression matrix for story 10 (endpoint-authorization): for every route, owner 200,
non-owner with no read 404, sharee with insufficient role 403, cross-tenant 404/422,
agent token on mutating routes 403, revoked/expired share denied immediately, group
removal denied on next request, Permit down 503, replay with same key idempotent, and a
schema walk proving no banned property name appears in any response.

## 15. Open questions and blockers

Hard prerequisites for FKY-3 (cannot be decided inside this docs-only spike):

- **Q3. Permit instance-role provisioning.** The policy delta (new actions `use`/`share`,
  new instance roles) needs the FuzeFront Security additive resource-role ingestion
  (referenced as FuzeFront #1389 in `docs/security/owner-grant-inventory.md`) and a
  decision on whether the backend workload may apply instance grants directly or only
  via the operator-reconciled outbox.
- **Q5. Approval schema.** `ApprovalRequest.agent_id` is NOT NULL with an FK to
  `agents.id` (migration `e4a1f0b21c01`), yet `BrokerService._enforce_approval` inserts
  `agent_id=0` (`service.py:446-451`). On PostgreSQL with FK enforcement that insert
  appears to violate the constraint unless an `agents` row with id 0 exists (unit tests
  on SQLite may not catch it). This needs verification now: it affects the existing
  high-sensitivity path, and human-initiated copy/move approvals need a nullable
  `agent_id` plus `requested_by_user_id`.
- **Q6. Custody adapters.** Only `OpenBaoKV2Vault` and `InMemoryVault` exist; there is no
  Vaultwarden adapter and no copy/rehome primitive.

Decisions for the security/product reviewer:

- **Q1.** Should `viewer` include `use`? Recommended yes (a viewer that can only list is
  not useful, and `use` yields only a short-lived broker credential). Conservative
  alternative: viewer is metadata-only and `use` starts at operator.
- **Q2.** Human raw `reveal`: keep on the existing custody reveal path, ACL-gated
  (recommended), or add a broker release kind (relaxes a core invariant).
- **Q4.** Confirm assumption A1 (org-user = org group vault).
- **Q7.** Who approves a human-initiated high-sensitivity copy/move: step-up
  re-authentication by the same user for personal targets, and an org owner/admin other
  than the requester for org targets (recommended).
- **Q8.** Confirm persona-grantee semantics (agent-only, capped at operator).

No blocker prevents merging these documents.
