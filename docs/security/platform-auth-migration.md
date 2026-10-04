# FuzeKeys platform authorization migration

Status: design and rollout prerequisite for `gate-platform-auth` Z1. This document does not grant access or change a running route.

## Current boundary

The gate reports 61 state-changing textual route matches and no platform permission decision call. An AST inventory finds 55 decorated POST, PUT, PATCH, and DELETE routes in `backend/app` (including compatibility aliases and login/OTP endpoints). The counts differ because the gate also reads route-shaped text outside decorators. Authentication and authorization are mixed today:

- Most user routes verify a FuzeKeys HS256 session through `get_current_user`; many account and identity handlers also constrain database queries by `Identity.user_id == current_user.id`.
- Broker routes use their own service and macaroon boundaries. Credential routes use `verify_api_key` plus `require_identity_scope`.
- Connector routes use the published FuzeFront machine-token verifier through `delegated_auth`: a workload token and a delegation token must have matching actor, target `service:fuzekeys`, and the required connector scope. Credential storage is partitioned by the delegated subject and provider.
- Public registration, login, device enrollment, and inbound OTP callbacks cannot require an already established user session. They need explicit enrollment or callback controls.

These controls must stay in place during migration. A global `/authz/check` middleware before identity federation and grant provisioning would turn existing valid requests into denials and would mishandle enrollment callbacks.

## Identity and policy prerequisites

1. Register a stable FuzeKeys tenant in FuzeFront Security. The existing Helm workload declaration and backend projected ServiceAccount token (audience `fuzefront-security`) already let the backend exchange its pod identity at `/api/v1/security/tokens/workload`; no reusable client secret is required. Verify that TokenReview resolves `service:fuzekeys` in the deployed namespace and that the exchanged token is accepted by `/api/v1/security/authz/check`. Configure the tenant ID and Security URL explicitly in production. The existing workload ConfigMap declares only vault credential scopes; Security currently requires a valid machine token for `authz/check` and does not define a separate check scope.
2. Define one immutable mapping from each FuzeKeys `User.id` to a FuzeFront subject and tenant. Persist it with uniqueness on the FuzeFront pair; never derive authority from a user-supplied ID, email, or project name. Existing FuzeKeys sessions contain only the local integer ID. FuzeFront's verified `/api/v1/security/session` response provides a stable `userId` but currently returns `tenantId: null`, so that response alone cannot establish tenant membership. Link accounts only with simultaneous proof of both sessions and separately verified tenant membership, then plan existing-user backfill, conflicts, and account merges before changing login issuance. A fixed application tenant configured by the operator constrains checks but does not prove a human belongs to it.
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
