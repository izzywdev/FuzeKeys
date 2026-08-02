# FuzeKeys — repo overlay (L1)

This repo **extends** the FuzeSDLC baseline (L0) at `izzywdev/FuzeSDLC` → `CLAUDE.baseline.md` (`baselineRef: main`). The baseline governs unless this file overrides it. Do not duplicate the baseline here — only repo-specifics live below. The agent/skill roster and hardening for this repo are declared in [`.fuze/manifest.json`](.fuze/manifest.json).

## Position
- **Class:** `oss-public` — public, **MIT** licensed, open contribution. Do **not** ship any non-MIT / proprietary license here.
- **Tier:** `product`.
- **Expert:** **`fuzekeys-expert`** — consult it first on any task to load architecture/PII-tokenizer/gotcha context (it advises, it does not gate).

## What this repo is
FuzeKeys is a **keys / secrets / PII-tokenization product** — an intelligent identity & account-management system that stores encrypted digital identities under a user-controlled master key and keeps raw PII/secrets out of the LLM data path.
- **Backend:** Python / FastAPI (async) + SQLAlchemy + **Alembic** migrations; Playwright/OpenAI automation.
- **Frontend:** React 18 + TypeScript + Tailwind. **Mobile:** React Native (`mobile/`).
- **PII Tokenizer** (`pii-tokenizer/`): Vault-encrypted, Redis-stored tokens with a 24h TTL; enforced at a LiteLLM `pre_call` guardrail and Claude Code Pre/PostToolUse hooks. Preserve the **tokenize-before-send** and Vault-encryption invariants on every change; never log raw PII or widen what reaches an LLM provider.
- `modules/` vendors `FuzeInfra` / `FuzeFront` / `EnvManager` as submodules — infra changes are delegated to FuzeInfra via `@claude`, never made from here.

## Auth — FuzeKeys authenticates nobody

**AuthN and AuthZ are delegated wholly to the FuzeFront Security API.** FuzeKeys holds no session signing key, stores no user password, and evaluates no policy. Which identity provider or authorization engine sits behind that API is FuzeFront's private implementation detail and **must never be named or reached from this repo** — not in code, not in config, not in a Helm value.

- **Backend seam:** `backend/app/security/` (`require_identity`, `get_current_user`, `require_permission`). `get_current_user` still returns the local `User` row so every FK keeps working — that row is a *projection* of a FuzeFront subject, not a credential store.
- **Frontend seam:** `frontend/src/services/securityClient.ts`, on the **same-origin** base (`/v1/security/*`). Never an absolute host — it breaks under local TLS and pins the app to one environment.
- **Authorization** uses `POST /v1/security/authz/check` (or `/bulk-check`) with the **bare** resource/action keys from `registration/policy.json` (`Identity:read`, `VaultAsset:reveal`, …). Never an engine-specific policy identifier.
- **Everything fails closed.** Unreachable service, unparseable body, absent tenant, mismatched bulk-decision length → deny. An authorization layer that opens when it breaks is worse than none, because it is trusted.
- **Do not invent endpoints.** If FuzeKeys needs something the security contract (`packages/security/openapi.yaml` in FuzeFront) has no operation for, that is a **contract gap to raise with FuzeFront** — never a direct call to some other system.

**The vault master key is NOT authentication.** It is FuzeKeys' domain secret: it decrypts the vault, FuzeFront never sees it, and it is verified in `app/utils/encryption.py` behind `/api/v1/auth/vault/{setup,unlock}`. It used to ride along on the login form; that was a conflation, not a design. `bcrypt` here is for that key alone.

**`permit.io` in `backend/app/integrations/site/` is a TARGET SITE, not auth.** FuzeKeys automates account creation on third-party SaaS sites; `permit.io` is one of them, exactly like `google.com`. Those references are product domain. Deleting them removes a capability.

## Hardening & delivery (repo-specifics)
- This repo is **already hardened** — the active "Protect default branch" ruleset, Harden Gate, signed commits, the standard automation stack, and nightly reconciliation are in place. Don't re-apply them.
- **`deployOnPush: false`** — no deploy-on-push on this repo. Prod is GitOps; never hand-deploy to prod.
- Finish work as a **merged PR** with signed commits; follow the baseline's done-contract and verification protocol.
