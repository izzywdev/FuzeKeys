#!/usr/bin/env python
"""PostToolUse hook: tokenize PII/secrets in the tool result BEFORE it enters the model's context,
via hookSpecificOutput.updatedToolOutput. Emits only when something changed.
Fail-open: any error -> no output -> original result is used (note: this means a stack outage
lets raw tool output through; acceptable for local dev, revisit for fail-closed later)."""
import sys
import os
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        return
    resp = data.get("tool_response")
    if resp is None:
        return
    try:
        import pii_vault as pv
        updated = pv.tokenize(resp) if isinstance(resp, str) else pv.tokenize_obj(resp)
    except Exception:
        return
    if updated != resp:
        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "updatedToolOutput": updated,
        }}))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
