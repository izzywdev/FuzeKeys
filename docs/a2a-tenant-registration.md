# A2A onboarding — a per-product pod in this chart

## Correction (2026-09-02): the "no pod here" analysis below is stale

This doc originally concluded FuzeKeys should onboard as a `tenants[]` entry on
FuzeAgent's shared `a2a-shared` server rather than run its own pod, because
`agent-templates/a2a/card_generator.py`'s callable endpoint was a **hardcoded
constant** (`IN_CLUSTER_URL = "http://a2a-shared.fuzeagent.svc.cluster.local:8080/rpc"`)
with no per-product override. That was true when written. **It is no longer
true.** FuzeAgent's contract v1.2.0 (PR #148) made the endpoint read
`a2a.inClusterUrl` from the values document, defaulting to the old constant only
when the value is unset — verified directly against
`agent-templates/a2a/card_generator.py` on FuzeAgent's default branch
(`_interface(..., in_cluster_url: str | None = None)`, `url = in_cluster_url or
DEFAULT_IN_CLUSTER_URL`). A per-product pod that sets its own `inClusterUrl` now
publishes an address callers can actually reach.

**Decision, updated:** FuzeKeys runs its own single-tenant A2A pod —
`deploy/helm/fuzekeys/templates/a2a.yaml`, values in
`deploy/helm/fuzekeys/values.yaml` under the `a2a:` key (+ `a2aDeploy:` for pure
chart mechanics, kept out of the frozen block per the same convention FuzeBI
uses). This is config-only variation over the one shared image
(`ghcr.io/izzywdev/fuze-a2a` — **not** `fuzeagent-a2a`; that name is a stale
pre-rename spelling that happens to still resolve on GHCR, but the contract's
authoritative name is `fuze-a2a`, `agent-templates/contracts/a2a/v1/schema/values-interface.schema.json`
`properties.a2a.properties.image.properties.repository.default`). No new image,
no product logic added to it.

The original reasoning below is kept for history but its "no pod" conclusion no
longer holds; do not re-derive an onboarding plan from it without re-checking
`card_generator.py` first, the way this correction did.

## Why a per-product pod was originally rejected (now outdated)

The published image was believed to be built as **one multi-tenant server
only**, and the card generator was believed to make that structural rather than
conventional:

```python
IN_CLUSTER_URL = "http://a2a-shared.fuzeagent.svc.cluster.local:8080/rpc"
```

`_interface()` was believed to return that constant as the callable endpoint of
every non-external Agent Card, with `external: true` as the only branch (a
public tunnel URL). Per the correction above, `_interface()` now takes an
`in_cluster_url` parameter sourced from `a2a.inClusterUrl` and only falls back
to the constant when it is unset.

**Still true, and not affected by the correction:** A2A is not an "LLM →
REST/OpenAPI" bridge. It reads no OpenAPI document and proxies no REST call. It
is a JSON-RPC 2.0 agent-delegation server whose Agent Card is *projected* from
`.fuze/manifest.json` plus `agent-templates/roles/<role>/role.json`. The
OpenAPI-to-tools job belongs to the MCP gateway, which is genuinely per-product
and is deployed by this same chart (`templates/mcp-gateway.yaml`).

## The pod this repo now ships

`deploy/helm/fuzekeys/values.yaml` `a2a:` block, summarized:

```yaml
a2a:
  enabled: false   # gate 1 of 2 — see "What's still pending" below
  image:
    repository: ghcr.io/izzywdev/fuze-a2a
    tag: <pinned SHA-12, resolved against the GHCR registry, never `latest`>
  service: { type: ClusterIP, port: 8080 }
  inClusterUrl: http://a2a-fuzekeys.fuzekeys.svc.cluster.local:8080/rpc
  auth:
    oidcIssuerUrl: https://app.fuzefront.com/application/o/fuzefront/
    audience: a2a
    callerClaim: repo
  tenants:
    - tenant: FuzeKeys
      repo: izzywdev/FuzeKeys
      ref: master
      enabled: true
      entryRole: keys-broker
      external: false
      provider:
        name: anthropic
        apiKeySecretRef: { name: a2a-provider-anthropic, key: api-key }
```

`templates/a2a.yaml` refuses to render (Helm `fail`) if the tag is empty/`latest`,
if `inClusterUrl` disagrees with the chart's own `a2a-fuzekeys` Service, or if
`tenants[]` does not have exactly one `enabled: true` entry — the same
fail-closed guards FuzeBI's chart uses, adapted to this repo's names.

## What's still pending (operator/GitOps, not code)

1. **`a2a-provider-anthropic` SealedSecret.** `kubeseal` is namespace-scoped, so
   it must be sealed into the `fuzekeys` namespace specifically — this is an
   operator step, never done by an agent, and never by copying another repo's
   sealed value. Until it exists, `a2a.tenants[0].provider.apiKeySecretRef`
   names a secret that does not resolve, and `gate-a2a --creds` correctly flags
   that rather than silently passing.
2. **Chart-level `a2a.enabled` stays `false`** until (1) lands, mirroring
   FuzeBI's own convention: fully wire the config, but don't schedule a pod that
   would crash-loop on a Secret that doesn't exist.
3. **Fleet Anthropic credit.** The shared Anthropic workspace has separately
   reported a low credit balance; even a correctly sealed pod may not serve
   until that's resolved. Not a FuzeKeys-specific gap and not fixed here.

None of this blocks the **card**: `.fuze/manifest.json` `a2a.enabled: true` +
this role's completed projection inputs mean FuzeKeys' Agent Card projects
correctly today. It is the **pod** — actual traffic-serving — that needs (1)-(3).

## Where the values come from

Every key under `a2a` in `values.yaml` is exactly the frozen operator interface
(`agent-templates/contracts/a2a/v1/schema/values-interface.schema.json`,
`additionalProperties: false` at every level — nothing here is invented). Pure
deployment mechanics (replica count, the git-sync init container image, the
git-token secretRef if this were a private repo) live in the sibling
`a2aDeploy:` block, which the interface deliberately does not define. Secret
values never appear in values; every `*SecretRef` is a `{name, key}` pointer to
a SealedSecret-provisioned Secret.

Reference: `agent-templates/contracts/a2a/v1/schema/values-interface.schema.json`
(frozen, in FuzeAgent) and FuzeSDLC `governance/a2a-runtime-standard.md`.
