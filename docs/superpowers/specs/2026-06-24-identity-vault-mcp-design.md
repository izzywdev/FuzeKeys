# Identity Vault + MCP Secrets Broker — Design

**Date:** 2026-06-24
**Status:** Approved design (pre-implementation)
**Author:** Claude (session e1f46be7-c51a-4d1e-9c4e-9f885635722d), with izzywdev

## 1. Goal

Give FuzeKeys an enterprise-grade, self-hosted store for **rich synthetic identities**
(name, address, phone, credit cards, SSN/passport and other custom PII fields) plus their
**site logins, service accounts, and API tokens**, and expose them to LLM agents over **MCP**
so agents can *request* credentials/tokens (and *store* ones they create) under policy —
without FuzeKeys implementing its own cryptography.

## 2. Hard constraints

- **Fully open-source, self-hostable, no managed services, no paid tiers.** This rules out
  Infisical (advanced RBAC/approval workflows are paid + phone-home) and any cloud offering.
- FuzeKeys must **not implement its own field-level cryptography** — delegate that to the
  adopted vault product.
- Must not regress the access-control hardening already merged (IDOR scoping, fail-closed
  auth, audit logging).

## 3. Locked decisions

| # | Decision | Choice |
|---|----------|--------|
| 1 | Vault role | Unified human-identity vault **+** machine/agent secrets, behind one MCP |
| 2 | Agent access model | **Policy-scoped auto-release + human approval for sensitive secrets** |
| 3 | System of record for secrets | **The vault products** (Postgres keeps only non-secret metadata + handles) |
| 4 | Product architecture | **Vaultwarden** (identity PII + logins) **+ OpenBao** (machine/API tokens) **+ new MCP broker** |
| 5 | Tenant isolation | **Single Vaultwarden silo**; isolation enforced by the broker's scope checks + Postgres tenancy + collection ACLs (logical, not cryptographic) |
| 6 | Hierarchy | **Organization → Users → Identities(personas) → {SiteLogins, Cards, API tokens}** (no workspace layer) |
| 7 | Persona ownership | **Private to the owning user**; org admins manage; an agent is bound to a user and limited to that user's personas (further scoped) |
| 8 | Agent capability | **Read + store newly-created credentials** (policy-gated, audited). No delete / full-CRUD in v1 |
| 9 | Approval channels | In-app approval queue **+ Telegram + Slack + Email** (pluggable notifier) |

### Why these products (build-vs-adopt)

- **Vaultwarden** (OSS, Rust, Bitwarden-API compatible) natively provides the rich field types
  we need — **Identity** items (name/address/phone; SSN/passport/license), **Card** items
  (hidden number/CVV), **Login** items (username/password/TOTP), and **custom fields**
  (text/hidden/boolean) — with **client-side encryption we never implement**. Sensitive PII
  (SSN/passport) is stored as **hidden custom fields + master-password re-prompt** because the
  built-in identity fields are not hidden by default. Free, self-hosted, all org/collection
  features unlocked.
- **No password manager models an enterprise multi-tenant application graph** (and
  Vaultwarden's own org/RBAC is explicitly aimed at small/personal use). So we **build** the
  tenancy graph in Postgres and use Vaultwarden purely as the encrypted payload store.
- **OpenBao** (MPL-licensed OSS fork of HashiCorp Vault) holds machine/agent API tokens with
  policy + audit, avoiding HashiCorp's BSL licensing. A dedicated instance keeps the
  agent-secrets domain separate from the existing PII-tokenizer transit Vault.

## 4. Architecture

```
 LLM agent ──MCP/HTTP (agent token)──▶  Secrets-Broker MCP service ──▶ Policy engine (scope + sensitivity)
                                              │                            ├─ in-scope + LOW/MED ─▶ auto-release
                                              │                            └─ HIGH ─▶ approval queue ─▶ notifier ─▶ human
                  ┌───────────────────────────┼───────────────────────────────┐
                  ▼                            ▼                               ▼
            Vaultwarden                  OpenBao (KV v2)                 FuzeKeys Postgres
        (Identity/Card/Login items,     (API tokens, service           (tenancy graph + handles,
         hidden custom fields;          secrets; per-agent policy;      agents/scopes, approvals,
         broker reads via bw serve)     audit device)                   audit index — NO secrets)
```

**Components**
1. **Secrets-Broker MCP service** — new standalone Python microservice; the only thing agents
   talk to. Owns agent auth, scope enforcement, sensitivity classification, approval
   orchestration, federation to Vaultwarden + OpenBao, and audit. Never returns a secret
   without a passing policy check and an audit record.
2. **Vaultwarden** — containerized; SoR for identity PII + logins + cards. Broker reads/writes
   through a local `bw serve` API using a least-privilege service account.
3. **OpenBao** — containerized; SoR for API tokens/service secrets (KV v2), per-agent ACL
   policies, audit device, auto-unseal (pattern mirrors the existing pii-tokenizer Vault).
4. **FuzeKeys Postgres** — tenancy graph + non-secret metadata + handles only.

## 5. Data model (Postgres — relational, no secret material)

| Table | Purpose | Key relations |
|---|---|---|
| `organizations` | Top tenant (company) | — |
| `users` | A person (John, Steve) | — |
| `organization_members` | M:N user↔org **+ role** (owner/admin/member) | person may belong to multiple orgs |
| `identities` | Persona; **metadata only** + `vault_collection_ref` | `org_id`, `owner_user_id` |
| `site_logins` *(formerly `accounts`)* | Per-site login metadata + `vault_item_ref` | `identity_id` |
| `identity_cards` | Card metadata (last4, brand, exp) + `vault_item_ref` | `identity_id` |
| `api_credentials` | API token/service-secret metadata + `openbao_path` | `identity_id` |
| `agents` | MCP machine identities (hashed token, bound `user_id`) | `user_id` |
| `agent_scopes` | What an agent may access (identity/site/secret-type) | `agent_id` |
| `approval_requests` | Sensitive-release workflow | `agent_id`, `resource_ref`, status, ttl |
| `audit_log` | Every access decision (no secret values) | indexed |

**Secret material (never in Postgres):**
- Each **Identity** → a Vaultwarden **Collection** holding one **Identity item** (name/address/
  phone; SSN/passport/etc. as **hidden custom fields**), N **Card items**, and the **Login
  items** for its sites. Postgres stores only the collection/item handles.
- Each **API token / service secret** → an **OpenBao** KV path, referenced from `api_credentials`.

**Cardinalities:** Org 1→N Users (M:N via membership); User 1→N Identities; Identity 1→N
{SiteLogins, Cards, API tokens}. Personas are private to `owner_user_id`.

**Example (John & Steve at Acme):** `organizations`=Acme; `users`=John,Steve;
John → 5 `identities`, Steve → 3; each identity → its SiteLogins/Cards/API tokens, with PII
in its Vaultwarden collection and tokens in OpenBao.

## 6. MCP interface (Secrets-Broker tools)

Agent token is bound to a user + scope. **Discovery returns metadata only; values are policy-gated.**

- `list_identities()` → personas in scope (id, display name)
- `list_site_logins(identity_id)` / `list_api_tokens(identity_id)` → names/sites/status, no values
- `get_identity_profile(identity_id, fields)` → non-sensitive PII auto; SSN/passport → approval
- `get_site_login(identity_id, site, fields)` → username/password
- `get_totp_code(identity_id, site)` → **current TOTP code, never the seed**
- `get_card(identity_id, card_id)` → HIGH → approval
- `get_api_token(identity_id, service)` → HIGH → approval (configurable)
- `store_site_login(identity_id, site, fields)` → **write**: persist a credential the agent just
  created (policy-gated, audited); also creates the Vaultwarden Login item + Postgres metadata
- `check_approval(request_id)` → on approve, returns a **one-time, short-TTL** value

Sensitive calls return `{status:"approval_required", request_id, expires_at}` until approved.
Transport: standalone **Python MCP server over HTTP (streamable)**, bearer agent token.

## 7. Security & policy

- **Agent auth:** token stored **hashed** (same pattern as the merged device-key fix), bound to
  `user_id` + scope; rotatable; fail-closed on unknown/blank token.
- **Scope check = the tenant boundary:** every call resolves agent → user, asserts the target
  identity is `owner_user_id == agent.user_id` **and** within `agent_scopes`. Cross-user /
  cross-tenant ⇒ hard deny + audit. Because the Vaultwarden silo is shared, this check is the
  isolation boundary and gets the heaviest test coverage.
- **Sensitivity tiers → release policy (configurable per org):**
  - LOW (metadata, display name) — auto
  - MEDIUM (site password, TOTP code) — auto in-scope, audited
  - HIGH (API tokens, cards, SSN/passport, service secrets) — **human approval required**
- **Approval flow:** HIGH ⇒ `approval_requests` row ⇒ **notifier** (in-app queue + Telegram +
  Slack + email, pluggable) ⇒ approve/deny ⇒ one-time short-TTL release or deny/timeout.
- **Audit:** every release (auto or approved) logged: agent, on-behalf user, identity, resource,
  decision, timestamp — **never the secret value**. Plus rate-limiting + anomaly alerting.
- **Secret hygiene:** TLS only; minimal fields; TOTP as codes not seeds; broker holds
  least-privilege Vaultwarden session + scoped OpenBao token; secrets never logged.

## 8. Migration & cutover

1. Stand up Vaultwarden + OpenBao + broker (empty).
2. One-time migration: decrypt existing Fernet `Account`/`ApiKey` rows → create Vaultwarden
   Login/Identity/Card items + OpenBao KV entries → write handles back to Postgres.
3. Cut over `credentials.py` (and the new MCP) to read via the broker; **remove the Fernet
   secret columns** from Postgres (keep Fernet decrypt only for the migration window).
4. Verify audit + scope on the new path; decommission the old columns.

## 9. Deployment & componentization

- **Secrets-Broker MCP** = standalone containerized Python microservice with its own client
  package; config via env/secrets (no secrets in repo).
- **Vaultwarden** + **OpenBao** = containers with persistent volumes + auto-unseal (mirrors the
  existing `pii-tokenizer/` Vault pattern).
- Delivered as docker-compose service definitions consistent with the repo's existing
  `docker-compose.*.yml` and `pii-tokenizer/` layout; Helm/Argo GitOps wiring follows if/when
  FuzeKeys moves to Kubernetes.

## 10. Testing strategy

- **Authorization seam (highest priority):** exhaustive cross-user / cross-tenant / out-of-scope
  denial tests — a test that fails if scoping is removed (same discipline as the IDOR
  regression tests).
- **Approval workflow:** sensitive ⇒ pending ⇒ notify ⇒ approve/deny/timeout ⇒ one-time TTL.
- **Audit completeness & no-secret-in-logs.**
- **MCP contract tests** for each tool; **store_site_login** round-trip.
- **Migration** correctness (decrypt→vault→handle, no data loss; columns removed).

## 11. Non-goals (v1)

- Agent **delete** / full CRUD of personas.
- Per-tenant cryptographic isolation (single silo chosen).
- Browser-autofill UX for agents (humans use normal Bitwarden clients against Vaultwarden).
- Dynamic/rotating secrets in OpenBao (possible later).

## 12. Implementation streams (for the plan)

Contract-first: freeze the **MCP tool contract + REST API** first, then fan out —
data-tier (schema/migrations/roles: **database-engineer**), broker service
(**backend-engineer**), notifier integrations, approval UI (**frontend-engineer**),
independent authorization/approval/audit tests (**test-engineer**), and container/deploy
wiring (**devops-engineer**).
