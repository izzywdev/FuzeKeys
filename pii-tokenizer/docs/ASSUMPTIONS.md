# Assumptions, Security Model & Limitations

## Threat model / what this protects

The goal is to keep raw PII and secrets **out of the upstream LLM provider** (Anthropic/OpenAI) and
out of the model's context window, while letting local tools still operate on real values. The model
reasons over stable opaque tokens; only local, trusted components (the proxy on loopback, the Claude
Code hooks, and Vault) ever handle plaintext.

**Trust boundary:** everything on `localhost` (proxy, Redis, Vault, Presidio, hooks) is trusted; the
LLM provider is not. Redis stores **only Vault ciphertext** — a Redis dump is useless without Vault.

## Core assumptions

1. **Vault is the only place real values can be recovered.** Redis holds `token → {ciphertext,type}`
   and `valhash → token` (dedup). The plaintext is never written to Redis or to disk by this code.
2. **Detection is allow-listed.** Only the entities in `PII_ENTITIES` plus the regex
   `SECRET_PATTERNS` are tokenized. Anything not matched passes through in the clear — this is a
   redaction tool, not a guarantee of total leak prevention.
3. **Tokens are stable and idempotent.** The same value always maps to the same token (valhash), and
   emitted `<TYPE_id>` tokens are not re-detected, so tokenizing already-redacted text is a no-op.
   This keeps multi-turn conversations and repeated tool calls consistent.
4. **Prompt redaction lives at the proxy, not in a hook.** Claude Code's `UserPromptSubmit` hook can
   only *block* a prompt or *add context* — it cannot rewrite the prompt. So prompts are tokenized by
   the LiteLLM `pre_call` guardrail on `:4000`. If the proxy is bypassed, prompts are not protected.
5. **Hooks are fail-open.** If Redis/Vault/Presidio is unreachable, the hooks emit nothing and the
   original tool input/output is used. This favors availability over secrecy — see Limitations.

## Detection precision: the identifier guard

Presidio scores `PHONE_NUMBER` at a flat ~0.4 for *both* real phone numbers and numeric fragments of
identifiers (e.g. the `4-5-20251001` inside `claude-haiku-4-5-20251001`). A score threshold alone
cannot separate them. The **identifier guard** in `pii_vault.py` (`_in_identifier`) drops any
numeric-entity match whose surrounding alphanumeric run contains a letter — i.e. it is part of an
identifier/version/code, not standalone PII. This is what makes a low threshold (0.4) usable without
corrupting model names, file paths, UUIDs, commit hashes, or version strings.

## Known limitations

- **The user's own typed prompt still shows real values on screen.** Tokenization happens at the
  proxy (the model never sees the real value), but no Claude Code hook can rewrite the *displayed*
  text of a user-submitted prompt — `UserPromptSubmit` can't rewrite it, and `MessageDisplay` only
  rewrites *assistant* message text. Tool outputs *are* shown tokenized (via PostToolUse). A
  permissioned, terminal-only "expose/reveal" of tokens (and any prompt-display masking) would need a
  future Claude Code capability or a wrapper layer.
- **Vault uses persistent file storage and survives restarts/reboots.** The transit key and all
  ciphertext live in the `pii-vault-data` volume, so a restart no longer orphans tokens. The
  tradeoff: persistent Vault is **sealed** on each start and must be unsealed. `stack-up.sh`
  auto-unseals from `vault/.vault-init.json`, which holds the single unseal key **and** the root
  token in cleartext on disk — appropriate for a localhost-only trust model, but it is the crown
  jewel: lose it and a sealed Vault is unrecoverable; leak it and all ciphertext is exposed. It is
  gitignored and must never be committed or synced. For multi-user/non-local use, move to multiple
  unseal shares or KMS auto-unseal and a transit-scoped token instead of root.
- **Tokens expire after 24h (`TOKEN_TTL=86400`).** Redis drops a token after a day; a `<TYPE_id>`
  referenced after expiry no longer detokenizes (it passes through literally). Set `TOKEN_TTL=0`
  for never-expire if you need detokenization across longer spans.
- **Fail-open by design.** A stack outage lets raw tool I/O through rather than blocking work.
  Make the hooks fail-closed if your threat model requires it.
- **Recall/precision is bounded by Presidio.** Misses (e.g. unusual formats) pass through; some
  benign standalone numbers that look like phone numbers (long digit runs, certain byte counts) can
  be tokenized. Tune `PII_ENTITIES` / `PII_SCORE_THRESHOLD`, or scope the PostToolUse matcher to
  specific tools, to trade recall vs. noise.
- **`US_SSN` may be tagged as `PHONE_NUMBER`.** Presidio classifies some SSNs (e.g. `078-05-1120`) as
  phone numbers at this threshold, so they tokenize as `<PHONE_…>`. Cosmetic — they are still redacted
  and restored correctly.
- **Latency.** PostToolUse runs Presidio on every tool result; `MAX_TOKENIZE_CHARS` bounds this by
  skipping very large outputs.

## Hardening checklist (before non-local use)

- Vault: persistent storage + auto-unseal; a token scoped to `transit/encrypt/pii` +
  `transit/decrypt/pii` only (not the root token).
- Redis: auth + TLS; consider a finite `TOKEN_TTL`.
- Hooks: decide fail-open vs. fail-closed deliberately.
- Keep `.env` out of version control (already gitignored) and inject secrets via your secret manager.
