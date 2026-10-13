# Decision record: vault sharing is a new ACL table, with the broker kept as the credential issuer

- Ticket: FKY-12 (design spike), parent FKY-3 (vault sharing)
- Status: **Proposed** - needs approval from at least one reviewer, including security, before FKY-3 starts (FKY-12 Definition of Done)
- Date: 2026-10-13
- Companion documents: [design](../design/vault-sharing.md), [frozen contract](../contracts/vault-sharing.v1.yaml)

## Context

FuzeKeys is single-owner today: `Identity.user_id` owns a persona and its assets
(`accounts`, `identity_cards`, `api_credentials`). FKY-3 needs user, persona, org and
org-user-group sharing, plus move and copy between vaults.

The only existing sharing-like mechanism is the broker core
(`backend/app/broker/`, table `broker_grants`). It is designed for secretless
agent-to-agent handoff. We must decide whether vault sharing is built by **extending that
grant model** or by a **new sharing/ACL table**.

Facts about the broker that drive the decision (all from the current code):

| Property of `broker_grants` / `BrokerService` | Where | Consequence for user sharing |
|---|---|---|
| A grant is bound to exactly one `redeemer_identity` string, compared by equality with the authenticated transport principal (`repo:...`, SPIFFE id, agent subject). | `service.py:262`, `identity.py` | Users, personas, orgs and groups are not transport principals. A group cannot be expressed as one string. |
| TTL is clamped to `max_ttl_seconds` (default 3600) and grants are `single_use` by default. | `service.py:183-185`, `runtime.py` | A share must last until revoked (weeks or months). Stretching grant TTL defeats the short-lived-credential property that is the broker's reason to exist. |
| Redeem releases a one-way derived credential (`fkderiv_...`, HMAC over the root) or an operation token, never a role-governed read. | `derived.py`, `service.py:297-330` | Nothing in a grant says "viewer / operator / admin". |
| Only the grantor identity can revoke; possession of `grant_id` is deliberately not authority. | `service.py:390-395` | An org admin cannot revoke a share a departed member created. |
| Grant rows are consumed by redemption and carry macaroon root keys. | `grant.py` | A "shared with me" listing would mix durable entitlements with consumed leases and operation grants. |
| Security invariants are proved by `backend/tests/test_broker_*.py` (non-disclosing denial, attenuation-only, transport identity only). | `README.md` | Changing grant semantics re-opens a proved security surface used by A2A callers. |

## Decision

**Add a new relational ACL (`vaults`, `vault_shares`, plus group tables) that answers
"who may read or operate this asset, in what role". Keep the broker, unchanged in
semantics, as the component that issues the actual short-lived credential when an
authorized principal accesses a shared asset.**

Division of labour, stated as an invariant for FKY-3:

> The ACL decides **whether** a principal may act on a vault asset. The broker decides
> **how** a value is released (short-lived, bound, single-use, human-gated when high
> sensitivity). The ACL never holds or returns a value; the broker never decides
> entitlement.

The single connection between them is an in-process lease: after the ACL (and Permit)
allow an access, the vault service calls `BrokerService.grant` with a system grantor and
the consumer's verified principal as `redeemer_identity`, TTL at most 60 seconds,
`single_use=True`, then `redeem`s it for the consumer. Revoking a share revokes the
leases issued under it. Details in design section 7.

## Options considered

### A. Extend `broker_grants` (rejected)

Add grantee types, long TTLs, role and group expansion to `Grant`.

Rejected because:

1. It breaks the grant's defining binding (one authenticated transport principal) and
   would need a parallel "principal type" system bolted onto the macaroon `redeemer =`
   caveat.
2. It needs either unbounded TTLs (destroys the short-lived guarantee) or constant
   re-issuance by a background job (a new moving part that must run to keep access alive,
   and fails open or closed unpredictably).
3. It cannot express group/org expansion: membership changes would require rewriting
   macaroons or fanning out one grant per member, which is a snapshot with stale access.
4. Revocation authority is grantor-only by design; org-level administration needs
   "anyone with `share` on the resource". Loosening that weakens an invariant the A2A
   path relies on.
5. It entangles two lifecycles (durable entitlement vs ephemeral lease) in one table,
   and any change touches security-proved behaviour used by other repositories.
6. Move and copy have no analogue in the grant model at all.

What A would have given us - one revoke path and one audit trail - is preserved in B by
the lease link (revoking a share revokes its leases; both write `audit_log`).

### A'. ACL row holding one long-lived macaroon per share (rejected)

Rejected: a persisted bearer handle is a standing capability. If it leaks, the share is
usable by whoever holds it for the life of the share, which is strictly worse than an ACL
row that is evaluated against the authenticated principal on every access.

### B. New ACL table, broker as issuer (chosen)

- Durable, queryable, role-bearing entitlements; `received`/`granted` listings are plain
  indexed queries.
- Group/org expansion is evaluated live against `organization_members` /
  `org_group_members`, so removal from a group removes access on the next request.
- Maps directly onto the existing Permit `VaultAsset` resource and the repo's established
  two-layer pattern (SQL ownership/ACL selects the row; Permit makes the instance
  decision; see `backend/app/security/owner_authz.py`).
- Leaves broker invariants and tests untouched.

Costs accepted:

- One more authorization surface to test (mitigated by the test plan in the design doc).
- Permit instance roles need provisioning for shares; this needs a policy delta and
  FuzeFront Security support (design section 6.4, open question Q3).
- One small additive broker change in FKY-3: a nullable `broker_grants.vault_share_id`
  column so a share revocation can sweep its leases, plus a `lease()` convenience wrapper.

### C. Hybrid with no broker involvement (rejected)

ACL row plus direct value release by the vault service. Rejected: it recreates a second
secret-release path next to the broker, contradicting the broker doctrine that the
`SecretResolver` seam and derivation path are the only sanctioned ways a secret moves.

## Consequences

- Positive: bounded blast radius; broker proofs stay valid; revocation is immediate
  (local ACL is checked before Permit); agents can be excluded from all mutating routes
  by token kind.
- Negative: new tables and an outbox for Permit grants; revocation of a share cannot
  recall a value a grantee with `reveal` already copied (documented limitation).
- Neutral: the human "reveal raw value" release is not a broker derived credential. It
  stays on the existing reveal/custody path, ACL-gated (open question Q2).

## Security review checklist (for the approving reviewer)

- [ ] Roles and caps in design section 6.2 (viewer includes `use`; `reveal` only for
      admin; persona and org grantees capped at operator; no re-share in v1).
- [ ] Human-only mutating routes (agent tokens rejected).
- [ ] 404 for absent-or-invisible, 403 only for visible-but-forbidden (contract R3).
- [ ] Copy requires `reveal` on the source (design section 8.2).
- [ ] Fail-closed on Permit or custody outage (503, never allow).
- [ ] Open questions Q1-Q7 answered or accepted.

## Follow-on stories to create and link to FKY-3

See design section 14. None of them is part of this spike.
