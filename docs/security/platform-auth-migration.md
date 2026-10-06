# FuzeKeys platform authorization migration

Status: partial implementation for `gate-platform-auth` Z1. The fail-closed decision client and explicit dual-session linking code are implemented. Linking becomes available only after the database migration, trusted Security tenant proof, and real tenant configuration are deployed. Instance owner policy and dry-run grant inventory are implemented. Identity update/delete and account-stage update now enforce instance decisions after SQL ownership selection. Other route families, grant application and ongoing synchronization remain unfinished; this document grants no access and does not certify production rollout.

## Current boundary

The initial gate inventory reported 61 state-changing textual route matches and no platform permission decision call. Its AST inventory found 55 decorated POST, PUT, PATCH, and DELETE routes in `backend/app` (including compatibility aliases and login/OTP endpoints), before the new linking route. The counts differ because the gate also reads route-shaped text outside decorators. Authentication and authorization are mixed today:

- Most user routes verify a FuzeKeys HS256 session through `get_current_user`; many account and identity handlers also constrain database queries by `Identity.user_id == current_user.id`.
- Broker routes use their own service and macaroon boundaries. Credential routes use `verify_api_key` plus `require_identity_scope`.
- Connector routes use the published FuzeFront machine-token verifier through `delegated_auth`: a workload token and a delegation token must have matching actor, target `service:fuzekeys`, and the required connector scope. Credential storage is partitioned by the delegated subject and provider.
- Public registration, login, device enrollment, and inbound OTP callbacks cannot require an already established user session. They need explicit enrollment or callback controls.

These controls must stay in place during migration. A global `/authz/check` middleware before identity federation and grant provisioning would turn existing valid requests into denials and would mishandle enrollment callbacks.

## Identity and policy prerequisites

1. Register a stable FuzeKeys tenant in FuzeFront Security. The existing Helm workload declaration and backend projected ServiceAccount token (audience `fuzefront-security`) already let the backend exchange its pod identity at `/api/v1/security/tokens/workload`; no reusable client secret is required. Verify that TokenReview resolves `service:fuzekeys` in the deployed namespace and that the exchanged token is accepted by `/api/v1/security/authz/check`. Configure the tenant ID and Security URL explicitly in production. The existing workload ConfigMap declares only vault credential scopes; Security currently requires a valid machine token for `authz/check` and does not define a separate check scope.
2. Use the explicit dual-session linking flow documented below to persist an immutable mapping from each FuzeKeys `User.id` to a verified FuzeFront subject and tenant. Never derive authority from a user-supplied ID, email, or project name. Existing FuzeKeys sessions contain only the local integer ID. Plan existing-user backfill, conflicts, and account merges before changing login issuance. A fixed application tenant configured by the operator constrains checks but does not prove a human belongs to it.
3. Register the resource types and actions below in the authorization provider. Seed grants for existing owners and operators, verify their cardinality against database ownership, then enforce checks. A missing subject, tenant, resource, grant, malformed response, or Security outage must deny. Do not substitute `allow: true` on timeout.
4. Keep database owner predicates after adding platform decisions. The policy grants operation authority; the database predicate keeps row selection and credential access tied to the actual owner. For create operations, derive the owner from the authenticated identity, never request data.

## Route families and proposed policy contract

All names below are **proposed** policy schema entries; none should be treated as an existing grant. `self` means the canonical mapped user subject, while the resource key is derived server-side after loading the row and its owner.

| Routes | Resource and actions to register | Required grant and existing boundary |
| --- | --- | --- |
| `/api/v1/identities` POST, PUT, DELETE; `/api/v1/accounts` POST, PATCH | `FuzeKeysIdentity:{identity_id}` `create/update/delete`; `FuzeKeysAccount:{account_id}` `create/update` | `owner` grant to mapped user; create uses user's namespace, update/delete require current SQL ownership predicate. |
| `/api/google/signup/*`, `/api/v1/chat/signup`, `/api/v1/site-integrations/*` | `FuzeKeysAccount:{account_id}` `signup/signin/create_key`; `FuzeKeysIdentity:{identity_id}` `use` | Account or identity owner grant plus existing `get_current_user` and owner lookup. Never authorize from a submitted email alone. |
| `/api/v1/sites` POST, PUT, DELETE, import | `FuzeKeysSite:{site_id}` `create/update/delete/import` | Explicit `site-admin` or `site-editor` role; define whether sites are shared across the tenant before grants. List/read routes need a separate decision plan. |
| `/api/v1/background/*`, `/api/infrastructure/*`, `/api/sms/request-otp`, `/api/v1/automation/analyze`, `/api/v1/llm-scraper/*`, `/api/v1/chat/message` | `FuzeKeysJob:{job_id}` `create/cancel`; `FuzeKeysInfrastructure:{target_id}` `operate`; `FuzeKeysScraper:{site_name}` `generate/improve/delete/debug`; `FuzeKeysMessage:{conversation_id}` `create` | Mapped user `owner` for personal jobs and messages; explicit operator grant for global start/stop, infrastructure commands, and shared scraper deletion. Bound output and cost separately. |
| `/api/credentials/*` | `FuzeKeysCredential:{identity_id or account_id}` `request/store/validate` | Existing service API key must map to a FuzeFront workload subject; require that subject's credential action grant **and** `require_identity_scope`. No raw owner ID from the request can establish authority. |
| `/api/v1/broker/*` | `FuzeKeysSecret:{secret_id}` `grant/redeem/mint/revoke` | Workload subject plus existing macaroon audience/caveat checks; tenant and secret owner determined from the broker record. Never replace caveat enforcement with a broad role. |
| `/api/v1/connectors/{provider}` PATCH/DELETE and credential PUT | `FuzeKeysConnector:{delegated_subject}:{provider}` `configure/disconnect/write_credential` | Existing `delegated_auth` scope and actor binding remain required. Add provider-scoped policy grants only after the caller workload, delegated subject, and FuzeFront tenant are mapped. |
| `/api/v1/auth/register`, `/api/v1/auth/login`, `/api/sms/register-device`, `/api/sms/otp` | Enrollment/callback boundary, not a pre-existing user resource | Retain bounded enrollment, password/device/OTP proof, rate limits, and callback validation. Do not call a user policy check before the user is known. Document these as deliberate public or proof-based routes in route governance. |

Compatibility aliases (Gmail connector paths and duplicated function decorators) must use the same checks and resource key as their primary route. `demo/chat` needs a separate decision to remove it from production or give it an authenticated, limited resource; it must not inherit an operator grant by accident.

## Enforcement sequence

1. Use the tested Python `check_permission(subject, tenant, resource, action)` client for Security's frozen request/response contract. Exchange the existing projected ServiceAccount token at `/tokens/workload` and accept only `allow is true`; deny on transport, parse, token, or policy errors. Never expose either token to browsers. This client does not turn on route enforcement until verified subject mappings, tenant membership, and real grants exist.
2. Ship route-family tests that prove both a positive grant and denial for a different owner. Include Security outage, malformed response, unknown tenant, and alias paths. Add tests that pre-session enrollment still works with its own proof and limits.
3. Backfill subject mappings and grants, compare counts to FuzeKeys ownership records, then enable enforcement one route family at a time behind a server-controlled rollout flag. A disabled flag may only exist during migration with an explicit deadline and must not be used to make the security gate green.
4. Require a production canary for each family, audit decision IDs without logging tokens or secrets, then remove the migration flag. Re-run `gate-platform-auth --authz` and the full route inventory. Z1 clearance is a consequence of real enforced call sites, not an added name or a skipped check.

No production authorization migration is complete until the Security tenant, workload identity, subject mapping, policy schema, and grants above are provisioned and verified against live requests.

## Explicit account linking contract

`POST /api/v1/auth/platform-link` requires both the existing local `Authorization: Bearer <FuzeKeys session>` and a separate `X-FuzeFront-Session: <platform session>` header. It takes no subject, tenant, role, email, or callback URL from the caller. Do not log either header. Response `200` contains only `{subject, tenant}`; `403` means a proof was rejected, `409` means an immutable binding conflicts, and `503` means configured verification is unavailable. No session credential is persisted or returned.

The server calls the configured Security origin's `GET /api/v1/security/session?tenant=<FUZEKEYS_AUTHZ_TENANT>`, with redirects disabled and a three-second timeout. Security must verify the live session and prove canonical active SQL organization membership and an active organization. Only an exact matching `identity.tenantId` is accepted. Security versions that ignore the query and return `tenantId: null` cannot establish a link. An owner without an active membership is not sufficient. The org detail endpoint's owner fallback and provider member-list endpoints are deliberately not used as membership proofs.

The additive `b2026link01` migration creates `platform_identities`: one binding per local user and a unique `(subject, tenant)` pair. Repeating the same verified link is idempotent; this API cannot change or unlink it. Conflict resolution requires a separately reviewed administrative recovery process. Upgrade does not rewrite users, credentials, or sessions and is compatible with old pods. Downgrade discards only the new bindings, requiring explicit relinking after a subsequent upgrade.

Set Helm `config.authzTenant` to the real canonical organization UUID only after deploying Security's tenant-proof support and provisioning membership. Empty defaults fail closed for this optional linking endpoint. Existing login, connector custody, and health protocols remain usable before the linking dependency is deployed; this is not a deployment prerequisite for them.

Like direct credential routes, this interactive session boundary uses `include_in_schema=False` so the generated OpenAPI/MCP gateway never turns session submission into an agent tool. The route and response contract are documented here, and source authorization gates still inspect it. Linking neither creates grants nor enables route-policy enforcement: Z1 remains unfinished until the grant backfill and route-family rollout above are complete.


## First existing-instance mutation guards

`PUT /api/v1/identities/{id}`, `DELETE /api/v1/identities/{id}` and
`PATCH /api/v1/accounts/{account_id}/stages/{stage_id}` require the persisted
`PlatformIdentity` binding and an explicit Security allow decision before changing
any fields or committing. Local SQL ownership predicates remain in place.
The instance query matches the inventory exactly: `fuzekeys_Identity` with
`identity:<id>` or `fuzekeys_Account` with `account:<id>`. Stage authority uses
the persisted parent account ID. Missing/unverified binding or denied permission
returns 403; unavailable configuration, tenant mismatch or Security outage returns
503. No rollout flag disables these guards.

**Deployment prerequisite:** apply and verify the instance schema, immutable
user mappings and scoped owner grants before deploying this head. Existing owners
without that rollout will be denied on these three operations. This stacked work
is not independently production ready. Creation and its transactional grant
lifecycle, reads and all other mutating families still need implementation; the
platform authorization gate is not evidence of complete enforcement.
