# Changelog — Secrets-Broker contract

All notable changes to the Identity-Vault Secrets-Broker contract
(`openapi.yaml` + `mcp-tools.json`) are recorded here. The contract is the
fan-out gate; every change bumps `info.version` / `package.json` version
(semver) and ripples to all generated clients through the contract PR.

## [0.1.0] - 2026-06-26

Initial frozen contract — Phase 2 fan-out gate.

### Added
- OpenAPI 3.1 spec (`openapi.yaml`) for the Secrets-Broker REST API:
  - Discovery (metadata only): `GET /identities`, `/identities/{id}/site-logins`,
    `/identities/{id}/api-tokens`.
  - Policy-gated secret access: `GET /identities/{id}/profile`,
    `/site-logins/{site}`, `/site-logins/{site}/totp` (current code, never the seed),
    `/cards/{cardId}` (HIGH -> 202), `/api-tokens/{service}` (HIGH -> 202).
  - Write: `POST /identities/{id}/site-logins`.
  - Approval workflow: `GET /approvals/{request_id}` (one-time short-TTL value),
    `GET /approvals`, `POST /approvals/{request_id}/approve|deny`.
  - Management CRUD-lite: organizations, organization members, identities, agents,
    agent scopes, agent token rotation, and `GET /audit-log`.
  - `components/schemas` for every design Section 5 entity + all request/response
    bodies; sensitivity tiers (LOW/MEDIUM/HIGH) encoded; HIGH => approval.
  - `agentBearer` security scheme (hashed agent token, owner + scope enforcement);
    401/403/404/202 responses reflecting the security model.
- MCP tool contract (`mcp-tools.json`) for all 10 tools from design Section 6,
  field-aligned with the REST schemas.
- Spectral ruleset (`.spectral.yaml`), `package.json` scripts (lint / mock /
  gen:types), scoped `.npmrc`, and the generated TS types under `client/`.
