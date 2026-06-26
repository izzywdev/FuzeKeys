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

## Hardening & delivery (repo-specifics)
- This repo is **already hardened** — the active "Protect default branch" ruleset, Harden Gate, signed commits, the standard automation stack, and nightly reconciliation are in place. Don't re-apply them.
- **`deployOnPush: false`** — no deploy-on-push on this repo. Prod is GitOps; never hand-deploy to prod.
- Finish work as a **merged PR** with signed commits; follow the baseline's done-contract and verification protocol.
