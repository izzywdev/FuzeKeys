# PII Tokenizer Claude Code Hooks

This directory contains Claude Code hook scripts that integrate with the PII Tokenizer service to prevent raw secrets and PII from entering the LLM context.

## Overview

The PII Tokenizer service (`pii-tokenizer/service/app.py`) runs on `localhost:8099` and provides tokenization/detokenization endpoints. These hooks act as thin shims (stdlib-only Python scripts) that call the service to enforce data protection across the Claude Code lifecycle.

### How It Works

1. **Tokenizer Service** (`http://127.0.0.1:8099`): Uses Presidio + regex patterns to detect secrets (API keys, SSNs, credit cards, emails, phone numbers, JWTs, etc.) and replaces them with tokens (`<TYPE_id>` format). Tokens are stored in Redis with a 24h TTL; real values are encrypted in Vault.
2. **Fail-Open**: If the tokenizer service is unreachable, hooks emit no output and let the data through unchanged. Hook errors never block the user.
3. **Token Format**: Same real value → same token (deduplication via Redis); stale tokens (post-TTL) are unrecoverable.

---

## Hooks

### `userpromptsubmit_guard.py` — Block Raw Secrets in Prompts

**Trigger:** `UserPromptSubmit` hook event — fires when the user sends a prompt in Claude Code.

**Behavior:**
- Reads the prompt from stdin JSON.
- POSTs it to the tokenizer service at `/tokenize`.
- **If PII/secret is detected** (tokenized result ≠ input): writes a clear warning to stderr and **exits 2**, which causes Claude Code to reject the prompt with the error message displayed.
- **If nothing detected** or **service is unreachable**: exits 0 silently (fail-open).
- **Policy:** Block-and-warn. Unlike Pre/PostToolUse hooks, the UserPromptSubmit hook is read-only — it cannot rewrite the prompt in-place once displayed on-screen. So the hook enforces a user-action policy: if raw PII/secret is detected, the user must manually remove it and resend.

**Example stderr message:**
```
⚠ Your prompt contains a raw secret or PII (detected and would be redacted). 
Secrets and sensitive data cannot be auto-tokenized in-place by Claude Code hooks. 
Please remove the raw secret/PII and use a reference or placeholder instead (e.g., 'my API key' or '<API_KEY>'), 
then resend the prompt.
```

**No secret echoed:** The hook NEVER outputs the actual secret value — only a generic warning and guidance. This prevents accidental logging or display of the raw PII.

### `pretooluse_detokenize.py` — Detokenize Tool Input

**Trigger:** `PreToolUse` hook event — fires before a tool is invoked.

**Behavior:**
- Reads the tool input from stdin JSON.
- POSTs it to the tokenizer service at `/detokenize_obj`.
- If the result differs from the input (i.e., tokens were present and restored): emits `hookSpecificOutput` with the updated input.
- The tool then operates on real, unredacted values.
- **Fail-open:** Service error → no output → tool uses original input.

### `posttooluse_tokenize.py` — Tokenize Tool Output

**Trigger:** `PostToolUse` hook event — fires after a tool returns.

**Behavior:**
- Reads the tool output from stdin JSON.
- POSTs it to the tokenizer service at `/tokenize_obj`.
- If the result differs from the original output (i.e., PII/secrets detected): emits `hookSpecificOutput` with the tokenized output.
- The tokenized output enters the LLM context, protecting raw data.
- **Fail-open:** Service error → no output → original output used.

---

## Registration

Hook registration is declared in `pii-tokenizer/claude/settings.snippet.json`. To enable these hooks:

1. **Copy the snippet** from `settings.snippet.json` into your local Claude Code `settings.json`:
   ```bash
   ~/.claude/settings.json  # on Linux/macOS
   %APPDATA%\Claude\settings.json  # on Windows (or use chezmoi if you manage it)
   ```

2. **Replace placeholders:**
   - `<PYTHON>`: Full path to `python.exe` (NOT `pythonw.exe`).
   - `<REPO>`: Full path to this FuzeKeys repo.

3. **Example** (after substitution):
   ```json
   {
     "hooks": {
       "UserPromptSubmit": [{
         "matcher": "*",
         "hooks": [{
           "type": "command",
           "command": "\"C:\\Python311\\python.exe\" \"C:\\dev\\FuzeKeys\\pii-tokenizer\\hooks\\userpromptsubmit_guard.py\"",
           "timeout": 30
         }]
       }],
       ...
     }
   }
   ```

4. **Environment:** Set `TOKENIZER_URL_HOST` to override the default `http://127.0.0.1:8099` if the service runs elsewhere.

---

## Implementation Notes

- **Thin client, stdlib only:** No external dependencies — only `sys`, `json`, `os`, `urllib.request`. Runs cleanly under `python.exe` with no console flash.
- **Timeout:** Each hook call has a 30s timeout budget (hardened against service hangs).
- **Explicit flush:** Uses `sys.stdout.write()` + `.flush()` to ensure JSON reaches Claude Code even when running headless or under `pythonw.exe`.
- **Error handling:** All exceptions are caught; failures default to fail-open (no output, original data used).

---

## Prompt-Level vs Tool-Level Tokenization

- **UserPromptSubmit hook** (this directory): Blocks raw secrets in user prompts with a **read-only, block-and-warn** policy. Cannot rewrite the prompt in-place.
- **PreToolUse / PostToolUse hooks** (this directory): Dynamically detokenize input / retokenize output for tool calls.
- **LiteLLM pre_call guardrail** (`pii-tokenizer/pii_guardrail.py`): Runs **before** the request leaves Claude Code to Anthropic's API. If Claude Code is routed through the LiteLLM proxy (`ANTHROPIC_BASE_URL=http://localhost:4000`), the guardrail applies prompt-level tokenization as a final check. This is the **fail-closed** layer for prompt-to-Anthropic data path.

For maximum protection, enable both the UserPromptSubmit hook (user-level guard) and route Claude Code through the LiteLLM proxy (API-level guard).

---

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| Hook doesn't run | Settings not merged correctly, or paths wrong | Verify `settings.json` has the hook entry with correct absolute paths |
| Hook runs but allows raw secret through | Tokenizer service is down | Ensure `pii-tokenizer/service/app.py` is running and listening on :8099 |
| "Permission denied" on hook script | Windows UAC or missing `x` permission | On Windows, ensure `python.exe` is in PATH; on Linux/macOS, `chmod +x userpromptsubmit_guard.py` |
| Hook times out (> 30s) | Service is slow or hung | Restart the tokenizer service; increase `timeout` in `settings.json` if needed |
| Hook blocks every prompt | Service is always returning different text | Check tokenizer service logs for errors; may be a Presidio/regex misconfiguration |

---

## Development

To test a hook locally without the full Claude Code setup:

```bash
# Create a test JSON payload
cat > test_prompt.json <<EOF
{"hook_event_name": "UserPromptSubmit", "prompt": "My API key is sk-ant-secret12345"}
EOF

# Run the hook (with tokenizer service running)
python pii-tokenizer/hooks/userpromptsubmit_guard.py < test_prompt.json
echo "Exit code: $?"
```

Expected output if secret is detected (when service is running):
- stderr: `⚠ Your prompt contains a raw secret or PII...`
- exit code: `2`

If service is down:
- (no output)
- exit code: `0`
