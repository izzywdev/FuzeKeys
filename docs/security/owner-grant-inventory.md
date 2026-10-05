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

The canonical backend policy collector namespaces product resources with an
underscore. The older standalone Security copy uses a dot namespace. Resolve
that deployment-specific namespace migration and verify the actual policy
resource types before applying this inventory; never translate or apply it
silently to an incompatible policy service.

A verified binding records the linking event; it does not prove current tenant
membership or current authority to grant roles. Every proposed principal needs a
fresh authoritative membership and grant-authority check before application.
`ready` means the SQL ownership inventory is complete, never authorization to
apply it. The report explicitly requires current membership verification and
includes sorted counts plus a SHA-256 checksum of the canonical proposed grants
and rejections for review. The checksum covers the snapshot, not later changes.
