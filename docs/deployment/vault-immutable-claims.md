# Vault immutable claim metadata

On 2026-10-07, Argo `fuzekeys-platform` attempted revision
`30c36352779be4b0d8d726fc3e994cda85b11ee9` but was OutOfSync/Degraded.
[Read-only query 37613761047](https://github.com/izzywdev/FuzeInfra/actions/runs/37613761047)
reported a forbidden StatefulSet spec update. The existing Vault remained ready.

[Read-only query 37613914971](https://github.com/izzywdev/FuzeInfra/actions/runs/37613914971)
confirmed that `spec.volumeClaimTemplates[0].metadata.labels` retained chart
`fuzekeys-0.1.15` and application `0.1.12`. The template had incorrectly derived
these immutable labels from each release's chart and application versions.

Production now explicitly preserves the full installed label map in
`vault.persistence.claimLabels`. This is immutable storage identity, not the
current image version. New installations use stable identity labels only.
Other existing installations must set this value to their own verified installed
map before upgrading. Do not clear or change an installed map during a release.

The change does not delete/recreate Vault, its StatefulSet or either PVC; it does
not use Force/Replace, read secrets, alter storage size/class, or widen access.
Chart version advances to 0.1.22; appVersion stays 0.1.18 because this is a
deploy-only fix for the already-built release.

Run `python3 scripts/__tests__/test_vault_claim_metadata.py` with Helm on PATH
(or set `HELM_BINARY`). Tests render the actual chart, compare production against
the observed immutable metadata and storage spec, exercise fresh installations,
and verify that future chart/app version bumps leave immutable fields unchanged.

After ordinary merge/checks, verify Argo Synced/Healthy, actual backend image
0.1.18, migrations and GET `/health` with `google-shared-v1`. Only then rerun the
FuzeFront release and production connector smoke tests. A green chart test or
image build alone is not production success.
