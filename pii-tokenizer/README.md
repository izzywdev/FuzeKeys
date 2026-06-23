# PII Tokenizer

Tokenization vault for PII and secrets in the Claude/LLM data path. Real values (credit cards,
SSNs, emails, phone numbers, IBANs, API keys/tokens) are **detected, encrypted, and replaced with
opaque placeholders** like `<CCD_ab12cd34ef56>` or `<APIKEY_…>` before any text leaves the machine
for the model. The ciphertext lives in Redis; the real value is recoverable only via HashiCorp
Vault. Tools transparently get the real value back when they actually need it.

```
                         ┌──────────────────────────────────────────────┐
   you type a prompt ───▶│ LiteLLM proxy :4000  (pii_guardrail, pre_call)│──▶ Anthropic / OpenAI
   (with real PII)       │   tokenize() → model sees <CCD_…>/<EMAIL_…>    │     (only ever sees tokens)
                         └──────────────────────────────────────────────┘
   model replies, calls a tool that contains <CCD_…>
                         ┌──────────────────────────────────────────────┐
                         │ Claude Code PreToolUse hook                   │
                         │   detokenize() → tool runs on the REAL value  │
                         └──────────────────────────────────────────────┘
   tool returns PII
                         ┌──────────────────────────────────────────────┐
                         │ Claude Code PostToolUse hook                  │
                         │   tokenize() → result re-enters chat redacted │
                         └──────────────────────────────────────────────┘
```

## Components

| Path | Role |
|------|------|
| `docker-compose.yml` | Redis (token store) + Vault (transit encryption, **persistent file storage**) + Presidio analyzer (PII detection over HTTP). |
| `vault/config.hcl` | Vault server config (file storage at `/vault/file`, TCP listener, tls disabled). |
| `stack-up.sh` | **Entry point.** Idempotent: waits for Docker, brings containers up, initializes Vault once, auto-unseals, and bootstraps the transit `pii` key. Run this instead of `docker compose up`. |
| `start-pii-stack.cmd` / `register-pii-task.ps1` | Windows auto-start at logon (Startup-folder launcher / elevated scheduled-task registration) so Vault is unsealed automatically after a reboot. |
| `bootstrap.sh` | Transit-only bootstrap (enable engine + create `pii` key). Folded into `stack-up.sh`; kept for manual use. |
| `pii_vault.py` | Shared library: `tokenize()` / `detokenize()` (+ `_obj` recursive variants). Presidio + secret regexes → Vault-encrypt → Redis. |
| `pii_guardrail.py` | LiteLLM `CustomGuardrail` (`pre_call`) — tokenizes prompt messages at the proxy so the upstream LLM only sees tokens. |
| `hooks/pretooluse_detokenize.py` | Claude Code PreToolUse hook — detokenizes tool **input** (`updatedInput`). |
| `hooks/posttooluse_tokenize.py` | Claude Code PostToolUse hook — tokenizes tool **output** (`updatedToolOutput`). |
| `litellm/` | Example LiteLLM config (guardrail wiring) + launcher that puts this dir on `sys.path`. |
| `claude/settings.snippet.json` | Hook + env registration to merge into Claude Code `settings.json`. |
| `test_pii_vault.py` | Round-trip test: tokenize → assert Redis holds ciphertext only → detokenize restores. |

## Quickstart

```bash
cp .env.example .env            # stack-up.sh fills in VAULT_TOKEN on first run
./stack-up.sh                   # docker up + Vault init/unseal + transit bootstrap (idempotent)
python test_pii_vault.py        # expect: ROUND-TRIP OK
```

Vault uses **persistent storage** and must be unsealed on each start; `stack-up.sh` auto-unseals
from `vault/.vault-init.json` (gitignored). Tokens carry a **24h TTL** by default (`TOKEN_TTL`).

To unseal automatically after every reboot, register the logon auto-start — see
**[docs/INSTALL.md](docs/INSTALL.md)**. Then wire it into LiteLLM and Claude Code (same doc).

## How detection works

- **Presidio** detects structured PII (`CREDIT_CARD`, `US_SSN`, `EMAIL_ADDRESS`, `PHONE_NUMBER`,
  `IBAN_CODE`) above a configurable score threshold.
- **Regex `SECRET_PATTERNS`** (in `pii_vault.py`) catch API keys / tokens Presidio doesn't cover
  well: `sk-ant-…`, `sk-proj-…`, `sk-…`, `AKIA…`, `ghp_…`, `xox[baprs]-…`, and JWTs.
- An **identifier guard** drops numeric matches that are glued to letters (e.g. the
  `4-5-20251001` inside `claude-haiku-4-5-20251001`), so version strings, IDs, and code aren't
  mangled as phone numbers. This is why a low score threshold (0.4) is safe.

Same value → same token (Redis `valhash` dedup), and emitted tokens are never re-detected, so
re-running `tokenize()` on already-redacted text is a no-op.

See **[docs/ASSUMPTIONS.md](docs/ASSUMPTIONS.md)** for the security model, trust boundaries, and
known limitations (including why the *user's own typed prompt* still shows real values on screen).
