#!/usr/bin/env python3
"""PostToolUse hook. Claude Code sends JSON on stdin after every tool call
succeeds. We just record it -- this hook never blocks anything."""

import sys
import os
import json
import datetime

sys.path.insert(0, os.environ.get("CLAUDE_PROJECT_DIR", os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from blackbox.db import get_conn

def main():
    raw = sys.stdin.read()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        sys.exit(0)  # malformed input, fail open, never break the agent

    session_id = data.get("session_id", "unknown")
    tool_name = data.get("tool_name", "")
    tool_input = json.dumps(data.get("tool_input", {}))[:2000]   # truncate huge inputs
    tool_output = json.dumps(data.get("tool_response", {}))[:2000]

    conn = get_conn()
    conn.execute(
        "INSERT INTO events (session_id, timestamp, hook_event, tool_name, tool_input, tool_output, decision) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (session_id, datetime.datetime.now(datetime.timezone.utc).isoformat(), "PostToolUse", tool_name, tool_input, tool_output, "allow"),
    )
    conn.commit()
    conn.close()
    sys.exit(0)  # always allow -- this hook only logs

if __name__ == "__main__":
    main()
