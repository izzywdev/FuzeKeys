# Installation

End-to-end setup of the PII tokenizer for Claude Code routed through a LiteLLM proxy.
Tested on Windows 11 (PowerShell + Git Bash) with Python 3.11 and Docker Desktop; the pieces are
OS-agnostic but the Windows-specific gotchas are called out.

## Prerequisites

- **Docker** (Compose v2) — runs Redis, Vault, and Presidio.
- **Python 3.11+** with `pip install redis` (the library uses only `redis` + the stdlib; it talks
  to Vault and Presidio over `urllib`, so no `hvac`/`requests` needed).
- **LiteLLM** proxy (`pip install 'litellm[proxy]'`) if you want prompt-level tokenization.
- **Claude Code** for the tool-level detokenize/tokenize hooks.

## 1. Bring up the supporting services

```bash
cp .env.example .env
./stack-up.sh               # docker up + Vault init/unseal + transit bootstrap (idempotent)
```

`stack-up.sh` waits for the Docker daemon, runs `docker compose up -d` (pii-redis :6379,
pii-vault :8200, pii-presidio :5002), then:

- **Initializes Vault once** (1 unseal share) and saves the unseal key + root token to
  `vault/.vault-init.json` (**gitignored — the crown jewels**).
- **Auto-unseals** from that file on every run (persistent Vault is sealed on each start).
- **Syncs `VAULT_TOKEN`** in `.env` to the persistent root token.
- **Ensures** the transit engine + `pii` key exist.

Vault uses **persistent file storage** (the `pii-vault-data` volume + `vault/config.hcl`), so the
transit key and all tokens survive container restarts and host reboots.

Verify:

```bash
docker ps --filter name=pii-          # all three healthy/running
python test_pii_vault.py              # ROUND-TRIP OK
```

`test_pii_vault.py` proves the contract: after `tokenize()`, **Redis holds Vault ciphertext only**
(every value starts with `vault:`), and `detokenize()` restores the original exactly. Tokens carry
a **24h TTL** (`TOKEN_TTL=86400`) and auto-expire from Redis.

### Auto-unseal at logon (survive reboots)

Persistent Vault comes back **sealed** after a reboot, so register `stack-up.sh` to run at logon.
Two options:

- **No admin (Startup folder)** — drop a hidden launcher in
  `%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup` that runs `start-pii-stack.cmd`:

  ```vbscript
  ' PII-Stack.vbs
  CreateObject("WScript.Shell").Run "cmd /c ""<REPO>\pii-tokenizer\start-pii-stack.cmd""", 0, False
  ```

- **Scheduled task (needs elevation once)** — from an **elevated** PowerShell:

  ```powershell
  .\register-pii-task.ps1     # registers the "PII-Stack" AtLogon task
  ```

Both run `stack-up.sh`, which waits for Docker Desktop to start, then unseals + bootstraps.

## 2. Prompt-level tokenization (LiteLLM proxy)

The `UserPromptSubmit` Claude Code hook **cannot rewrite the prompt** (see ASSUMPTIONS.md), so prompt
redaction happens at the proxy that Claude Code routes through.

1. Put this directory on the proxy's import path. The provided `litellm/litellm_launcher.py` does it
   for you:

   ```python
   sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..") )  # -> pii-tokenizer/
   ```

   (Adjust the path so `pii_guardrail` and `pii_vault` are importable, or set `PYTHONPATH`.)

2. Register the guardrail in your LiteLLM config (see `litellm/litellm_config_lite.example.yaml`):

   ```yaml
   guardrails:
     - guardrail_name: pii-tokenizer
       litellm_params:
         guardrail: pii_guardrail.PIITokenizer
         mode: pre_call
         default_on: true
   ```

3. Start the proxy and point Claude Code at it (in `settings.json` `env`):

   ```json
   "env": {
     "ANTHROPIC_BASE_URL": "http://localhost:4000",
     "ANTHROPIC_API_KEY": "sk-litellm-master-local-dev"
   }
   ```

The guardrail fires on both `/v1/chat/completions` (OpenAI) and `/v1/messages` (Anthropic — the path
Claude Code uses). Confirm by sending a request with a unique fake email and checking that a new
`valhash:` key appears in Redis.

### Windows notes
- Set `PYTHONUTF8=1` and `PYTHONIOENCODING=utf-8` for the proxy process — LiteLLM's startup banner
  crashes under the default cp1252 console encoding otherwise.
- Launch the proxy with **`pythonw.exe`** (not `litellm.exe`) so it has no console and survives
  `CTRL+C`/terminal signals; redirect stdout/stderr to separate files.

## 3. Tool-level detokenize / tokenize (Claude Code hooks)

Merge `claude/settings.snippet.json` into your Claude Code `settings.json`, replacing `<PYTHON>`
with your `python.exe` and `<REPO>` with this repo's absolute path:

- **PreToolUse** (`matcher: "*"`) → `hooks/pretooluse_detokenize.py` — swaps `<TYPE_id>` tokens in
  tool input back to real values so the tool operates on real data.
- **PostToolUse** (`matcher: "*"`) → `hooks/posttooluse_tokenize.py` — tokenizes PII in tool output
  before it re-enters the model's context.

Use **`python.exe`, not `pythonw.exe`**, for these — they must write their JSON result to stdout.
Hooks load at Claude Code startup, so **restart Claude Code** after editing settings.

> If your `settings.json` is managed by **chezmoi**, edit the chezmoi *source*
> (`.../chezmoi/dot_claude/settings.json`) and run `chezmoi apply`; a session-end sync will
> otherwise revert direct edits.

## 4. Verify end-to-end

In Claude Code, have it `Bash echo` a fake credit card and read it back: you should see a `<CCD_…>`
token in the transcript, while the tool itself received the real number (via the PreToolUse hook).

## Teardown

```bash
docker compose down          # stop containers; KEEP volumes (tokens + Vault key persist)
docker compose down -v       # also drop pii-redis-data AND pii-vault-data volumes
```

`down -v` destroys the persistent Vault storage. After that you must delete the stale
`vault/.vault-init.json` and re-run `stack-up.sh` (it will re-initialize a fresh Vault); every
previously issued token becomes permanently undecryptable.
