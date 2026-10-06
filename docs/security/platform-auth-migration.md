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


## Google identity-bound operations

`POST /api/google/signup/{identity_id}` now requires an explicit
`fuzekeys_Identity:use` decision for `identity:<id>` after SQL ownership verification
and before constructing the browser signup service. `POST
/api/google/test/identity-conversion/{identity_id}` requires `Identity:read` on the
same instance before any conversion/decryption. The repository and Helm policy
copies declare `use` only on the Identity instance owner's role; no tenant-wide
role receives it. These calls retain verified immutable platform bindings and
fail closed on a missing/denied grant or unavailable Security response.

Register the updated `use` action and verify actual owner decisions before
rolling out these guards. Existing unlinked owners cannot run these operations.
This extension checks two additional identity-backed POST operations; it does
not certify the remaining route families or the account-create grant lifecycle.
Manual Google signup has no persisted owned instance and remains outside this
adapter. The Google account list now requires Identity:read and an individual
Account:read allow on every owned returned row before decrypting any response.
Signup persists the actual Account model's website and encrypted email/notes
fields; account status is projected from is_active/signup_completed. The API
keeps the existing email/status/metadata response keys without plaintext database
storage. New account grants still require the verified inventory/provisioning
lifecycle before reads can succeed. The Google OAuth connector custody path is
separate from these browser signup automation routes.

The owner provisioning client also verifies an explicit Identity:use allow canary
for every Identity grant, in addition to read/update/delete and the unassigned
principal denial. A stale policy that omits the new signup action stops the run
without marking that grant verified. No Google authorization claim follows from
unit testing this prepared application path.

## Tenant-isolated delegated connector custody

Connector custody is a separate `fuzekeys_Connector` resource. The instance key
is `connector:` plus lowercase SHA256 of UTF-8 compact JSON
`[verified_tenant, verified_subject, canonical_provider]` (non-ASCII preserved).
The same tuple is persisted in SQL, recomputed by read-only inventory and checked
by the operator client. Instance owner permissions are read, create, configure,
disconnect, reveal and write_credential; no tenant role receives these actions.
The SDK verified tenant is mandatory. No local User ID, email, body tenant or
VaultAsset policy can establish connector authority.

Migration `c2026conn01` adds nullable tenant IDs, replaces owner/provider
uniqueness with tenant/owner/provider uniqueness and creates a non-secret grant
intent outbox. Existing NULL tenant rows and their vault paths are left untouched
and cannot be queried by tenant-bound handlers. Reconnect with verified tenant
proof is required; no guessed tenant backfill runs. Downgrade refuses tenant-bound
custody rather than discarding isolation. Old pods must be retired before changing
the owner/provider uniqueness contract; mixed-version writes are not safe.

First credential PUT with a trusted delegation creates only scoped owned
metadata and an owner intent in one SQL transaction, then returns HTTP 202
`{status:"authorization_pending",provider,resource_key,retry_after_authorization:true}`.
It stores no submitted credential, email, scopes or configuration and does not
call the vault. This is registration, not an authorization allow or a connected
integration. After reviewed operator provisioning, an explicit repeated PUT
requires create and write_credential instance decisions before vault custody.
Existing connected writes require write_credential. Read/configure/disconnect/
lease require their exact instance decisions before response or vault work.
Pending credential leases fail 409; missing/denied permissions fail 403 and
unavailable Security fails 503. The runtime only checks permissions using its
projected workload identity; it cannot call grant administration.

Vault paths, Google advisory locks, shared-account reads and deletion reference
counts include verified tenant and owner. Legacy unbound credentials are never
borrowed. A disconnect transaction records desired_state=absent in the outbox;
this is a reconciliation request, not evidence of provider grant revocation.
Deleting the custody row prevents reads even while an old policy grant remains.
Reconnection records desired_state=present for the same deterministic tuple.

Use `owner_grant_inventory.py --connectors --tenant <verified-tenant> --output <private-snapshot>` and
`apply_owner_grants.py --connectors` with the existing reviewed checksum, actual
tenant, fresh SQL connection and operator token requirements. NULL legacy rows
are excluded from tenant provisioning, never inferred. Intent/custody tuple
disagreement aborts; orphan/deleted intents cannot grant. The provisioner
recomputes provider hashes, sends connectorProvider metadata to Security's
dedicated owner-grant boundary, checks fresh canonical membership and verifies all
six owner actions plus foreign-principal denial. Revocation intents require
separate reviewed operator reconciliation; the existing provider grant IDs are
not safe automatic revoke handles. Production registration, live mappings,
policy ingestion and positive/cross-tenant canaries remain required before rollout.

## Existing owned read guards

Identity detail and identity list require exact `fuzekeys_Identity:read` instance
decisions before decrypting or projecting rows. The account list requires both
`fuzekeys_Account:read` and `fuzekeys_Identity:read` for each account and the parent
identity name it includes. Every row in the requested page is checked before any
response object is constructed; one denial rejects the whole page. SQL owner
filters and bounded pagination stay in place. Lists retain local owner counts;
they do not claim to enumerate or count only policy-authorized resources.
Denied/unlinked requests return 403 and Security outages return 503 without being
converted to generic 500 errors. Existing verified mappings and exact read grants
must be provisioned before deployment. Creates and their grant lifecycle remain
unfinished; these reads do not certify the complete authorization migration.

## Legacy credential AsyncSession repair

The legacy `/api/credentials` handlers now use the production `AsyncSession`
contract: awaited SQL selects/scalars/counts, awaited commits and rollback on
credential write/access transaction failure. Identity/account predicates and
static service-key identity scopes remain required before SQL or cryptography.
The GET credential alias uses the same checked read handler. Identity account
lists retain sorted bounded pagination and their existing response envelope.
Google OAuth connector records and VaultAsset inventory are separate storage
families and are not implicitly granted by this repair.

This repair restores functioning database operations; it does not establish
platform authorization for static service API keys. Those callers still need
verified workload principals, tenant mapping and explicit resource/action grants
before that family's authorization migration can be declared complete. No
credential-delete endpoint exists in this legacy router; this change introduces
no delete route or new authority. Production PostgreSQL and actual authenticated
service requests still need rollout verification.
