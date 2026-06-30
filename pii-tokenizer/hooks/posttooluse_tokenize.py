#!/usr/bin/env python
"""PostToolUse hook shim (host): tokenize PII/secrets in the tool result BEFORE it enters the
model's context, via the containerized tokenizer service (hookSpecificOutput.updatedToolOutput).

Thin client — stdlib only — so it runs under pythonw.exe with no console flash. Emits only when
something changed. Fail-open: any error -> no output -> original result is used (note: a stack
outage lets raw tool output through; acceptable for local dev, revisit for fail-closed later)."""
import json
import os
import sys
import urllib.request

TOKENIZER_URL = os.environ.get("TOKENIZER_URL_HOST", "http://127.0.0.1:8099")


def _call(path, payload):
    req = urllib.request.Request(
        TOKENIZER_URL + path,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode())


def _emit(obj):
    # Explicit write + flush so the JSON reaches Claude Code's pipe even under pythonw.exe.
    sys.stdout.write(json.dumps(obj))
    sys.stdout.flush()


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        return
    resp = data.get("tool_response")
    if resp is None:
        return
    try:
        # /tokenize_obj handles both strings and nested JSON (it recurses, tokenizing string leaves).
        updated = _call("/tokenize_obj", {"obj": resp})["obj"]
    except Exception:
        return  # service down -> fail open
    if updated != resp:
        _emit({"hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "updatedToolOutput": updated,
        }})


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
