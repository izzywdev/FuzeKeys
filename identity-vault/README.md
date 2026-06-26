# Identity-Vault Storage Backends (Phase 3)

Containerized, fully-OSS storage for the Secrets-Broker (design
`docs/superpowers/specs/2026-06-24-identity-vault-mcp-design.md`, §4 / §9). No managed
services, no payment.

| Service | Role | Host port |
|---------|------|-----------|
| **Vaultwarden** (`idv-vaultwarden`) | Encrypted identity PII, cards, site logins (Bitwarden Identity/Card/Login items + hidden custom fields). **Client-side crypto — we never implement field encryption.** | `8222` → 80 |
| **OpenBao** (`idv-openbao`) | Machine/agent API tokens & service secrets (KV v2 + ACL policy + audit). Truly-OSS (MPL) Vault fork — avoids HashiCorp BSL. | `8210` → 8200 |

Ports are offset from the existing `pii-tokenizer/` stack (which owns 8200/6379/5002), so the
two stacks run side-by-side.

## Quickstart
```bash
cd identity-vault
cp .env.example .env
# set VW_ADMIN_TOKEN (argon2 hash recommended — see .env.example)
./stack-up.sh        # docker up + OpenBao init/unseal + KV v2 mount + broker policy/token
```
`stack-up.sh` is idempotent (safe to re-run / run at logon). It:
1. brings the containers up,
2. initializes OpenBao once and saves the unseal key + root token to
   `openbao/.openbao-init.json` (**gitignored** — the crown jewel of the localhost dev trust
   model), auto-unsealing from it on every start,
3. enables the `kv/` (v2) mount and a file audit device,
4. writes the **`identity-broker`** policy (CRUD on `kv/data/identities/*` only) and mints a
   policy-scoped broker token into `.env` as `OPENBAO_BROKER_TOKEN`.

## How the broker (Phase 4) uses this
- **OpenBao:** reads/writes API tokens at `kv/identities/<identity_id>/<service>/<name>` using
  `OPENBAO_BROKER_TOKEN` (least-privilege; cannot touch other paths or the pii-tokenizer Vault).
- **Vaultwarden:** reads/writes Identity/Card/Login items via the Bitwarden API using a dedicated
  service account (`VW_SERVICE_EMAIL` / `VW_SERVICE_PASSWORD`), created in the UI after first run.
- The Postgres `vault_collection_ref` / `vault_item_ref` / `openbao_path` handles (Phase 1) point
  at items in these two stores.

## Security notes
- `SIGNUPS_ALLOWED=false` — no open registration; the broker/admin provisions accounts.
- Single OpenBao instance, separate from the pii-tokenizer transit Vault (different security
  domain; agent secrets ≠ PII-redaction transit keys).
- Tenant isolation is enforced by the broker's scope checks (single Vaultwarden silo, per design
  decision 5), not by per-tenant crypto.

## Production
These are local docker-compose definitions consistent with `pii-tokenizer/`. Helm/Argo GitOps
wiring (persistent PVCs, auto-unseal via a KMS, SealedSecrets for `VW_ADMIN_TOKEN` /
`OPENBAO_BROKER_TOKEN`) follows when FuzeKeys moves to Kubernetes (devops-engineer).
