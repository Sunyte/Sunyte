#!/usr/bin/env python3
"""PreToolUse hook. Runs BEFORE every tool call. Can block it by returning
permissionDecision: deny. This is the kill-switch / rule-enforcement layer."""

import sys
import os
import json
import datetime

sys.path.insert(0, os.environ.get("CLAUDE_PROJECT_DIR", os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from blackbox.db import get_conn
from blackbox.config import load_config
from blackbox.alert import send_alert


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


def record_flag(session_id: str, rule_name: str, severity: str, message: str):
    conn = get_conn()
    conn.execute(
        "INSERT INTO flags (session_id, rule_name, severity, message, timestamp) VALUES (?, ?, ?, ?, ?)",
        (session_id, rule_name, severity, message, datetime.datetime.now(datetime.timezone.utc).isoformat()),
    )
    conn.commit()
    conn.close()


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
    cfg = load_config()

    # --- Rule 1: hard-blocked tools ---
    if tool_name in cfg.get("blocked_tools", []):
        msg = f"Tool '{tool_name}' is on the hard-blocked list."
        record_flag(session_id, "blocked_tool", "block", msg)
        send_alert(f"Blocked tool call `{tool_name}` in session {session_id[:8]}.")
        deny(msg)
        return

    # --- Rule 2: dangerous Bash patterns ---
    if tool_name == "Bash":
        command = tool_input.get("command", "")
        for pattern in cfg.get("dangerous_bash_patterns", []):
            if pattern in command:
                msg = f"Command matched dangerous pattern: '{pattern}'"
                record_flag(session_id, "dangerous_bash", "block", msg)
                send_alert(f"Blocked dangerous command in session {session_id[:8]}: `{command[:100]}`")
                deny(msg)
                return

    # --- Rule 3: too many tool calls this session (proxy for runaway loop / spend) ---
    conn = get_conn()
    count = conn.execute(
        "SELECT COUNT(*) FROM events WHERE session_id = ?", (session_id,)
    ).fetchone()[0]
    max_calls = cfg.get("limits", {}).get("max_tool_calls", 200)
    if count >= max_calls:
        msg = f"Session has made {count} tool calls, exceeding limit of {max_calls}."
        record_flag(session_id, "max_tool_calls", "block", msg)
        send_alert(f"Session {session_id[:8]} hit the tool-call limit ({count}) and was stopped.")
        conn.close()
        deny(msg)
        return

    # --- Rule 4: session running too long ---
    row = conn.execute(
        "SELECT started_at FROM sessions WHERE session_id = ?", (session_id,)
    ).fetchone()
    conn.close()
    if row:
        started_at = datetime.datetime.fromisoformat(row[0])
        elapsed_minutes = (datetime.datetime.now(datetime.timezone.utc) - started_at).total_seconds() / 60
        max_minutes = cfg.get("limits", {}).get("max_session_minutes", 30)
        if elapsed_minutes >= max_minutes:
            msg = f"Session has run {elapsed_minutes:.1f} min, exceeding limit of {max_minutes} min."
            record_flag(session_id, "max_session_time", "block", msg)
            send_alert(f"Session {session_id[:8]} exceeded time limit and was stopped.")
            deny(msg)
            return

    # --- Rule 5: off-path tool (warn only, don't block) ---
    allowed = cfg.get("allowed_tools", [])
    if allowed and tool_name not in allowed:
        msg = f"Tool '{tool_name}' is outside the normal allowed set."
        record_flag(session_id, "off_path_tool", "warn", msg)
        send_alert(f"Off-path tool `{tool_name}` used in session {session_id[:8]} (allowed, just flagged).")

    allow()


if __name__ == "__main__":
    main()
