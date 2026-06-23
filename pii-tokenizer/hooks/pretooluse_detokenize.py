#!/usr/bin/env python
"""PreToolUse hook: detokenize `<TYPE_id>` placeholders in the tool input back to real values,
so the tool operates on real data. Emits hookSpecificOutput.updatedInput only when something changed.
Fail-open: any error -> no output -> Claude uses the original input (never blocks the tool)."""
import sys
import os
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        return
    tool_input = data.get("tool_input")
    if tool_input is None:
        return
    try:
        import pii_vault as pv
        updated = pv.detokenize_obj(tool_input)
    except Exception:
        return
    if updated != tool_input:
        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "updatedInput": updated,
        }}))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass  # never fail a tool call because of the hook
