# Instance owner grant migration dry run

FuzeKeys owns its policy declaration in `registration/policy.json`; the Helm
registration copy must match. Identity, Account and VaultAsset declare a resource
instance `owner` role. This role does not become a tenant role and grants no
permissions on another instance. This declaration requires the additive
resource-role ingestion contract in FuzeFront Security before registration.

Run `python scripts/owner_grant_inventory.py --output /private/inventory.json`
with `DATABASE_URL_ASYNC` for the intended database. The tool uses a PostgreSQL
read-only transaction, selects identifiers only and creates a new private file.
It never writes database rows or calls Security/Permit. An exit code of 2 means
ownership cannot be mapped safely: the report contains rejected resource keys and
no grant set. An empty database legitimately yields an empty inventory.

Ownership comes from Identity.user_id; Account.identity_id and
ApiCredential.identity_id join back to that identity. Only the immutable,
verified PlatformIdentity subject and tenant may become grant principals. Local
integer user IDs, email addresses, display names and org_id are not principals.
Orphan resources or unlinked users block the whole inventory. Mapping uses exact
instance keys `identity:<id>`, `account:<id>`, `api-credential:<id>` under resource
types `fuzekeys_Identity`, `fuzekeys_Account`, `fuzekeys_VaultAsset` respectively.
Future authorization guards must use these same keys.

The output is a review inventory, not a provider API payload or an approval to
apply grants. Review on a consistent production snapshot, reconcile every
rejection through explicit identity linking, register instance policies, and
provision exact grants through the trusted Security administration path. Prove
positive owner decisions and negative cross-owner/cross-tenant decisions before
enabling mutation guards. Re-run after ownership changes; this tool does not
implement continuous grant synchronization. Other resource families (Site,
SignupScript, ApiKey, identity cards, connectors and organizations) need their own
verified ownership migration before the complete Z1 gate can pass.

Runtime registration sends the repository declaration to the backend
`PUT /api/apps/fuzekeys/policy`, storing it in the application policy record.
The backend boot and Helm Permit schema job use the canonical underscore
namespace. Deploy the additive instance-role ingestion contract in FuzeFront
#1389 before registering these roles. The dormant standalone Security copy uses
a dot namespace, but it does not establish a migration prerequisite for this
runtime path. Verify the actual registered policy and exact instance resource
types through trusted live administration before applying any inventory.

A verified binding records the linking event; it does not prove current tenant
membership or current authority to grant roles. Every proposed principal needs a
fresh authoritative membership and grant-authority check before application.
`ready` means the SQL ownership inventory is complete, never authorization to
apply it. The report explicitly requires current membership verification and
includes sorted counts plus a SHA-256 checksum of the canonical proposed grants
and rejections for review. The checksum covers the snapshot, not later changes.

## Trusted application and canaries

`scripts/apply_owner_grants.py` now provides an explicit, resumable application
path. It requires the reviewed inventory SHA-256, the one intended tenant,
a production PostgreSQL connection, an operator token file, an HTTPS Security
origin and a new private journal. The default runs preflight only. `--apply`
creates only exact resource-instance `owner` tuples through Security; it never
uses Permit directly, assigns a tenant role, infers subjects or revokes grants.

First deploy Security's admin-only `GET /api/v1/security/authz/membership-proof`
and the fresh membership validation on FuzeKeys grant writes, plus #1389 policy
ingestion and the registered instance roles. The proof response must contain the
requested `subject`, `tenant` and boolean `active: true`. The grant endpoint must
independently verify current SQL membership and active organization, so a
membership revoked between preflight and grant cannot authorize that grant.
The operator must already possess the existing tenant-management authority;
this tool cannot acquire it.

For each run, the tool validates every resource namespace and positive numeric
instance key, refuses mixed tenants or malformed counts/checksums, re-reads the
SQL inventory before mutations and again before each grant, and proves all
principals' fresh membership before the first write. Run during an exclusive
ownership maintenance window: sequential SQL/API requests do not establish a
distributed transaction and cannot protect against an ownership change after a
snapshot read. This tool neither freezes ownership nor synchronizes future
creates/deletes. Any new or orphaned rows require a new reviewed inventory.

The tool records exact grant intent before network calls, acknowledged tuples
and completed canaries to a new mode-0600, fsynced journal. It then requires
explicit owner allow decisions for `read`, `update`, `delete` and an explicit
`update` denial for an unassigned canary principal. Additional production
cross-owner/cross-tenant canaries using real accounts remain required: an
unassigned principal does not prove every real principal lacks broader grants.
A provider failure or failed canary stops the run without reporting completion.
Changes acknowledged earlier in the run may remain; reconcile the journal and
provider decisions before retrying. No automatic rollback is safe here because
the current provider's grant IDs omit the resource instance, and its grant-list
projection drops instance fields. The script deliberately never revokes by those
ambiguous IDs or treats a lost response as proof the write failed.

Example operator invocation (token contents and database URL stay out of CLI
arguments and logs):

```sh
python scripts/apply_owner_grants.py \
  --inventory /private/inventory.json \
  --checksum <reviewed-sha256> \
  --tenant <canonical-tenant> \
  --token-file /private/operator-token \
  --security-url https://security.fuzefront.com \
  --journal /private/preflight.jsonl
```

After successful preflight and live schema verification, rerun with `--apply`
and a distinct journal file. This is a prepared provisioning path; no production
inventory, membership, grant or allow/deny decision was verified by developing
or unit-testing it. It covers only the three inventory resource families, not
the unfinished create lifecycle or other authorization route families.
