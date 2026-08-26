# A2A onboarding — a tenant entry in FuzeAgent, not a pod here

## Why there is no A2A pod in this repo's chart

The published image `ghcr.io/izzywdev/fuzeagent-a2a` is built as **one
multi-tenant server**, and the card generator makes that structural rather than
conventional. `agent-templates/a2a/card_generator.py` line 29:

```python
IN_CLUSTER_URL = "http://a2a-shared.fuzeagent.svc.cluster.local:8080/rpc"
```

`_interface()` returns that **constant** as the callable endpoint of every
non-external Agent Card. It is not values-driven, and no environment variable
overrides it — the only branch is `external: true`, which swaps in a public
`https://a2a.<repo-slug>.prod.fuzefront.com/rpc` tunnel URL.

So a per-product A2A Deployment would start, pass its health check, and publish a
card advertising the **shared** server's address. Every caller would dial
`a2a-shared.fuzeagent`, and the per-product pod would never receive a request. A
pod that looks healthy and is functionally dead is worse than no pod, because
nothing goes red.

FuzeAgent's own `docs/a2a/enable-your-pod.md` says the same thing in prose:
*"There is one shared A2A server for the whole family, not one deployment per
product... onboarding a repo is data, not a new chart."*

**Also worth correcting, because it drives the wrong design:** A2A is not an
"LLM → REST/OpenAPI" bridge. It reads no OpenAPI document and proxies no REST
call. It is a JSON-RPC 2.0 agent-delegation server whose Agent Card is
*projected* from `.fuze/manifest.json` plus `agent-templates/roles/<role>/role.json`.
The OpenAPI-to-tools job belongs to the MCP gateway, which **is** genuinely
per-product and **is** deployed by this chart.

## The tenant entry this product needs

Add to FuzeAgent `deploy/helm/a2a-shared/values-prod.yaml` under `a2a.tenants`:

```yaml
  - tenant: FuzeKeys
    repo: izzywdev/FuzeKeys
    ref: master
    enabled: true
    external: false
    entryRole: keys-broker
    servingRoles: [keys-broker]
    provider:
      name: anthropic
```

Both gates must be true to actually serve: `a2a.enabled` (the shared server is
deployed at all) and this tenant's own `enabled`.

## Preconditions this repo does NOT yet meet

These are the callee's own contract and every one of them **fails closed**. None
was worked around here.

1. ~~**`agent-templates/roles/keys-broker/role.json` has no `description`.**~~
   **RESOLVED (2026-08-21).** `role.json` was reshaped to the role contract and now
   carries a valid top-level `description` (the four skills folded into
   `a2a.examples`, `extendedOnly: true` added so a credential broker never appears
   on the anonymous agent card). Card projection is no longer blocked on this repo's
   side. `a2a-maintainer` still validates the projection against the frozen
   `contracts/a2a/v1` on every PR.

2. **`.fuze/manifest.json` already has a populated `providesTo`** (18 entries) —
   good. An absent or empty list means DENY EVERY CALLER (authz.md §3), so this
   product is ahead of its siblings here.

3. ~~**`.fuze/manifest.json` has `a2a.enabled: false`**~~ **FLIPPED to `true`
   (2026-08-26, owner instruction).** With precondition 1 resolved, the repo-local
   card-projection inputs are complete, so the flag was enabled. This is only the
   FIRST of the two serving gates: the SECOND — the FuzeKeys tenant entry in
   FuzeAgent's `a2a-shared` `values-prod.yaml` (the block shown above) — is a
   cross-repo change in `izzywdev/FuzeAgent` and is still OUTSTANDING. Until it
   lands, the shared A2A server has no FuzeKeys tenant to route to.

## Where the values come from

`tenant`, `repo`, `ref` and `enabled` are per-tenant. `auth.oidcIssuerUrl`,
`auth.audience`, `auth.callerClaim` and `cardSigning.keySecretRef` are
**server-level** and already belong to the shared deployment — this product does
not set them and must not carry a copy. Secret values never appear in values;
every `*SecretRef` is a `{name, key}` pointer to a SealedSecret-provisioned
Secret.

Reference: `agent-templates/contracts/a2a/v1/schema/values-interface.schema.json`
(frozen) and `docs/a2a/enable-your-pod.md`, both in FuzeAgent.
