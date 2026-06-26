# Identity Vault — Secrets-Broker Contract (Phase 2, frozen gate)

This is the **frozen contract** for the FuzeKeys identity-vault Secrets-Broker. Backend, UI,
and tests are all built against it (see design
`docs/superpowers/specs/2026-06-24-identity-vault-mcp-design.md`). Changes ripple deliberately:
amend via PR, don't diverge silently.

## Files
| File | Purpose |
|------|---------|
| `openapi.yaml` | OpenAPI 3.1 REST contract (23 paths, 46 schemas) — the broker implements this |
| `mcp-tools.json` | MCP tool contract (10 tools) the agent-facing MCP server exposes |
| `.spectral.yaml` | Spectral lint ruleset for `openapi.yaml` |
| `package.json` | scripts: `lint`, `mock`, `gen:types` |
| `client/` | generated TS types (`gen:types` output; consumed by UI/tests) |

## MCP tool ↔ REST endpoint mapping
| MCP tool | REST endpoint | Tier |
|----------|---------------|------|
| `list_identities` | `GET /identities` | metadata |
| `list_site_logins` | `GET /identities/{id}/site-logins` | metadata |
| `list_api_tokens` | `GET /identities/{id}/api-tokens` | metadata |
| `get_identity_profile` | `GET /identities/{id}/profile` | LOW auto · SSN/passport → approval |
| `get_site_login` | `GET /identities/{id}/site-logins/{site}` | MEDIUM (auto in-scope) |
| `get_totp_code` | `GET /identities/{id}/site-logins/{site}/totp` | MEDIUM — returns the **current code, never the seed** |
| `get_card` | `GET /identities/{id}/cards/{cardId}` | HIGH → approval |
| `get_api_token` | `GET /identities/{id}/api-tokens/{service}` | HIGH → approval |
| `store_site_login` | `POST /identities/{id}/site-logins` | write (policy-gated, audited) |
| `check_approval` | `GET /approvals/{request_id}` | — |

## Sensitivity & approval semantics
- **LOW** (metadata, display name) and **MEDIUM** (site password, TOTP code) release automatically
  *when in scope*, and are audited.
- **HIGH** (cards, API tokens, SSN/passport) return **HTTP 202** `{status:"approval_required",
  request_id, expires_at}`. The agent polls `GET /approvals/{request_id}`; once a human approves
  (in-app / Telegram / Slack / email), it returns a **one-time, short-TTL** value. Denied/expired
  requests never release.

## Security model (encoded in the spec)
- Agent auth: **bearer token** (`securitySchemes`), bound to a user + scope.
- The broker's scope check is the tenant boundary (single Vaultwarden silo): `401` bad/missing
  token, `403` out-of-scope / cross-tenant, `404` not found under the supplied owner, `202`
  approval required. No endpoint returns a secret without passing policy + writing an audit record.

## Consuming the contract
```bash
cd contracts/identity-vault
npm install              # spectral, prism, openapi-typescript (see package.json)
npm run lint             # spectral lint openapi.yaml
npm run mock             # prism mock server — UI/tests build against this, no backend needed
npm run gen:types        # openapi-typescript -> client/types.ts (shared types for UI/tests)
```
The backend implements `openapi.yaml`; the independent test suite asserts against the **same**
spec, so contract drift becomes a failure.

## Status
**Frozen** as the Phase 2 fan-out gate. Phases 3–5 (vault infra, broker, approval UI) build
against this. Validated: `openapi.yaml` and `mcp-tools.json` parse; field names/types are
consistent between the REST schemas and the MCP tool I/O.
