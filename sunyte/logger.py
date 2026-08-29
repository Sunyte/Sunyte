#!/usr/bin/env python3
"""PostToolUse hook. Claude Code sends JSON on stdin after every tool call
succeeds. We just record it -- this hook never blocks anything. Routed
through core.log_event so it's part of the same tamper-evident hash chain
as every other logged event."""

import sys
import os
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from sunyte.core import log_event

def main():
    raw = sys.stdin.read()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        sys.exit(0)  # malformed input, fail open, never break the agent

    session_id = data.get("session_id", "unknown")
    tool_name = data.get("tool_name", "")
    tool_input = json.dumps(data.get("tool_input", {}))[:2000]
    tool_output = json.dumps(data.get("tool_response", {}))[:2000]

    log_event(session_id, tool_name, tool_input, tool_output, decision="allow")
    sys.exit(0)  # always allow -- this hook only logs

if __name__ == "__main__":
    main()
