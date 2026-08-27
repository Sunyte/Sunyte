#!/usr/bin/env python3
"""PreToolUse hook. Runs BEFORE every tool call. Delegates the actual rule
checking to sunyte.core.check_guard - the SAME rule engine used by the
LangChain/custom-agent path - so every feature (dangerous patterns, regex,
protected paths, spend limits, tool-call/time limits) applies identically
here, without duplicating the logic."""

import sys
import os
import json

sys.path.insert(0, os.environ.get("CLAUDE_PROJECT_DIR", os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from sunyte.core import check_guard


def deny(reason: str):
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }))
    sys.exit(0)


def allow():
    sys.exit(0)  # no JSON, no decision -> normal permission flow applies


def main():
    raw = sys.stdin.read()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        allow()
        return

    session_id = data.get("session_id", "unknown")
    tool_name = data.get("tool_name", "")
    tool_input = data.get("tool_input", {})

    allowed, reason = check_guard(session_id, tool_name, tool_input)
    if not allowed:
        deny(reason)
        return
    allow()


if __name__ == "__main__":
    main()
