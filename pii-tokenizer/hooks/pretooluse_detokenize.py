#!/usr/bin/env python
"""PreToolUse hook shim (host): detokenize `<TYPE_id>` placeholders in the tool input back to real
values via the containerized tokenizer service, so the tool operates on real data.

Thin client — stdlib only — so it runs under pythonw.exe with no console flash. Emits
hookSpecificOutput.updatedInput only when something changed. Fail-open: any error -> no output ->
Claude uses the original input (never blocks the tool)."""
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
    tool_input = data.get("tool_input")
    if tool_input is None:
        return
    try:
        updated = _call("/detokenize_obj", {"obj": tool_input})["obj"]
    except Exception:
        return  # service down -> fail open
    if updated != tool_input:
        _emit({"hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "updatedInput": updated,
        }})


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass  # never fail a tool call because of the hook
