# FuzeKeys Secret Broker

Safe **agent-to-agent secret exchange** for FuzeOne. Agents never pass raw secrets
to each other. This module is **deterministic security infrastructure** — not an
LLM.

## Doctrine (best → fallback)

1. **Capability delegation (zero exchange).** If A needs something requiring a
   secret B holds, A asks B to *do* it. Grant an `operation`; redeeming it yields a
   scoped **operation token**, never a secret. B uses its own secret and never
   reveals it.
2. **Secretless handoff.** A non-secret **grant handle** (a macaroon) travels
   between agents. Each agent independently authenticates to FuzeKeys and redeems.
   The secret never transits the A2A channel, prompt, MCP arg, artifact, or logs.
3. **On redemption, release a short-lived DERIVED credential** — never the
   long-lived root, which never leaves the vault.

## Interface (`BrokerService`, deterministic core)

| Method | Purpose |
|--------|---------|
| `grant(secret_ref\|operation, redeemer_identity, scope, ttl, single_use, sensitivity)` | Returns an **opaque macaroon handle** — no secret material. TTL is clamped to the server max. |
| `redeem(ctx, handle)` | Authenticates the caller's **transport identity** (OIDC `repo` claim / mTLS-SPIFFE), verifies the grant is bound to it, not expired, not already used, not revoked, policy-permitted; releases a short-lived **derived** credential. Non-disclosing on any failure. |
| `mint_token(ctx, audience, scope, ttl)` | **RFC 8693** OAuth 2.0 Token Exchange (STS) — the secretless ideal. |
| `revoke(grant_id)` | Instant, idempotent, non-disclosing revocation. |

### Security invariants (proved by `backend/tests/test_broker_*.py`)

- redeemable **only** by the bound transport identity;
- TTL enforced (+ clamped to server max); single-use enforced; revoked grant fails;
- the **root secret is never returned** — only a derived credential;
- a caller-**asserted** identity is ignored (authz is always on the *authenticated*
  transport identity — mirrors A2A `authz.md` §1);
- **macaroon attenuation can only narrow** scope/TTL, never widen (multi-hop A→B→C);
- **denials are non-disclosing** (same message for "no such grant" and "not yours").

## Mechanisms (vetted libraries — no hand-rolled crypto)

- **Macaroons** (`pymacaroons`) — attenuable capability handles. `macaroons.py`.
- **Envelope encryption / KMS wrap-unwrap** (`cryptography`) — AES-256-GCM data key
  wrapped RSA-OAEP to the recipient's published JWK, so a secret can transit an
  untrusted relay decryptable only by the recipient. `envelope.py`.
- **Dynamic/derived secrets** + **RFC 8693 token exchange** (`python-jose`) — the
  root stays in the vault; redemption mints a scoped, short-TTL derived cred / a
  downstream exchanged token. `derived.py`.

Grounded in: RFC 8693 (token exchange), SPIFFE/SPIRE workload identity, macaroons
(Birgisson et al. 2014), and Vault/OpenBao dynamic-secrets + response-wrapping.

## Two surfaces

- **MCP tools** (`mcp_tools.py`): `keys.grant` / `keys.redeem` / `keys.mint_token` /
  `keys.revoke` — deterministic, for orchestrating agents.
- **A2A serving role** (`agent-templates/roles/keys-broker/role.json` + the
  `.fuze/manifest.json` `a2a` block): the policy-mediated / human-gated path. A
  high-sensitivity grant requires **human approval** (`reach_human` / digital
  persona) before release. `enabled:false` until `a2a-maintainer` validates card
  projection against the frozen `contracts/a2a/v1` and the tenant is registered.
- **HTTP** (`routers/broker.py`, `POST /api/v1/broker/*`): the transport the MCP
  server + A2A role sit on. Transport identity comes from gateway-verified headers
  (`X-Verified-Repo` / `X-Verified-Spiffe`) — **never** the request body.

## Vault seam

`vault.py` defines `SecretResolver`; `runtime.get_vault()` is the injection point.
Wire an **OpenBao** (KV v2 / transit) or **Vaultwarden** resolver in deployment.
An unconfigured broker fails closed (redeem of a `secret_ref` → non-disclosing
denial).
