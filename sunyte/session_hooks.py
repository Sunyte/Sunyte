#!/usr/bin/env python3
"""Handles SessionStart and SessionEnd. Wired to both events in settings.json;
dispatches based on hook_event_name in the payload."""

import sys
import os
import json
import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from sunyte.db import get_conn


def main():
    raw = sys.stdin.read()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        sys.exit(0)

    session_id = data.get("session_id", "unknown")
    event = data.get("hook_event_name", "")
    conn = get_conn()

    if event == "SessionStart":
        cwd = data.get("cwd", "")
        conn.execute(
            "INSERT OR IGNORE INTO sessions (session_id, started_at, cwd, status) VALUES (?, ?, ?, 'running')",
            (session_id, datetime.datetime.now(datetime.timezone.utc).isoformat(), cwd),
        )
        conn.commit()

    elif event == "SessionEnd":
        conn.execute(
            "UPDATE sessions SET ended_at = ?, status = 'completed' WHERE session_id = ?",
            (datetime.datetime.now(datetime.timezone.utc).isoformat(), session_id),
        )
        conn.commit()

    conn.close()
    sys.exit(0)


if __name__ == "__main__":
    main()
