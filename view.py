#!/usr/bin/env python3
"""Usage:
  python3 view.py sessions              # list recent sessions
  python3 view.py replay <session_id>   # frame-by-frame replay
  python3 view.py flags [session_id]    # show flagged/blocked events
"""
import sys
from sunyte.db import get_conn


def list_sessions():
    conn = get_conn()
    rows = conn.execute(
        "SELECT session_id, started_at, ended_at, status, total_cost_usd FROM sessions ORDER BY started_at DESC LIMIT 20"
    ).fetchall()
    conn.close()
    for r in rows:
        cost = r[4] or 0.0
        print(f"{r[0][:12]}  started={r[1]}  ended={r[2]}  status={r[3]}  spend=${cost:.5f}")


def replay(session_id):
    conn = get_conn()
    rows = conn.execute(
        "SELECT timestamp, hook_event, tool_name, tool_input, decision FROM events "
        "WHERE session_id LIKE ? ORDER BY timestamp ASC",
        (session_id + "%",),
    ).fetchall()
    conn.close()
    if not rows:
        print("No events found for that session id (try a prefix match).")
        return
    for i, r in enumerate(rows, 1):
        print(f"[{i}] {r[0]}  {r[2]}  decision={r[4]}\n    input={r[3][:200]}\n")


def flags(session_id=None):
    conn = get_conn()
    if session_id:
        rows = conn.execute(
            "SELECT timestamp, rule_name, severity, message FROM flags WHERE session_id LIKE ? ORDER BY timestamp",
            (session_id + "%",),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT timestamp, rule_name, severity, message FROM flags ORDER BY timestamp DESC LIMIT 50"
        ).fetchall()
    conn.close()
    for r in rows:
        print(f"{r[0]}  [{r[2]}] {r[1]}: {r[3]}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    cmd = sys.argv[1]
    if cmd == "sessions":
        list_sessions()
    elif cmd == "replay" and len(sys.argv) > 2:
        replay(sys.argv[2])
    elif cmd == "flags":
        flags(sys.argv[2] if len(sys.argv) > 2 else None)
    else:
        print(__doc__)
