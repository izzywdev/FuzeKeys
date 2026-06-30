#!/usr/bin/env python
"""UserPromptSubmit hook guard (host): detect raw secrets/PII in the user's prompt BEFORE it is
submitted to Claude Code's session, via the containerized tokenizer service.

Unlike PreToolUse/PostToolUse hooks (which can rewrite tool input/output), UserPromptSubmit is
read-only — the prompt is already displayed on-screen and cannot be rewritten in-place by the hook.
So this hook enforces a policy: block-and-warn if PII/secret is detected, and instruct the user
to remove it or use a reference instead.

Strategy: POST the prompt to the tokenizer service (/tokenize endpoint). If the tokenized result
differs from the input, something was detected and redacted — PII/secret is present.

Thin client — stdlib only. Fail-open: any service error -> exit 0 (never block on infrastructure).
30s timeout budget for the service call."""
import json
import os
import sys
import urllib.request

TOKENIZER_URL = os.environ.get("TOKENIZER_URL_HOST", "http://127.0.0.1:8099")


def _call(path, payload):
    """POST to tokenizer service with 30s timeout."""
    req = urllib.request.Request(
        TOKENIZER_URL + path,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())


def main():
    """Check the prompt for PII/secrets. Exit 2 + warn if detected, else exit 0."""
    try:
        data = json.load(sys.stdin)
    except Exception:
        # Malformed JSON on stdin — let it through, not our problem
        return 0

    prompt = data.get("prompt")
    if prompt is None or not isinstance(prompt, str):
        # No prompt field or it's not a string — nothing to check
        return 0

    # Empty prompt is fine
    if not prompt.strip():
        return 0

    try:
        # POST the prompt to /tokenize. If the service returns a DIFFERENT text,
        # it detected and redacted PII/secrets.
        tokenized = _call("/tokenize", {"text": prompt})["text"]
    except Exception:
        # Service unreachable, errored, or malformed response -> fail-open, don't block
        return 0

    if tokenized != prompt:
        # PII/secrets detected. Write a clear, user-facing message to stderr and exit 2.
        # DO NOT echo the raw secret value — only warn generically about what was found.
        msg = (
            "⚠ Your prompt contains a raw secret or PII (detected and would be redacted). "
            "Secrets and sensitive data cannot be auto-tokenized in-place by Claude Code hooks. "
            "Please remove the raw secret/PII and use a reference or placeholder instead (e.g., 'my API key' or '<API_KEY>'), "
            "then resend the prompt."
        )
        sys.stderr.write(msg + "\n")
        sys.stderr.flush()
        return 2

    # No PII/secret detected, or tokenizer returned the same text.
    return 0


if __name__ == "__main__":
    try:
        exit_code = main()
    except Exception:
        # Catastrophic failure — fail-open, don't block the user
        exit_code = 0
    sys.exit(exit_code)
