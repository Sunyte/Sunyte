#!/usr/bin/env python3
"""agent-blackbox CLI.

Usage:
  blackbox sessions                    # list recent sessions
  blackbox replay <session_id>         # human-readable timeline replay
  blackbox replay <session_id> --raw   # old raw per-field dump
  blackbox flags [session_id]          # show flagged/blocked events
  blackbox stats                       # total spend + call counts across all sessions
  blackbox verify                      # check the tamper-evident log chain is intact
  blackbox export <session_id>         # export one session's full audit trail as CSV
  blackbox report [--days N]           # human-readable compliance summary (default: 30 days)
"""
import sys
import csv
import json
import ast
import datetime
from blackbox.db import get_conn
from blackbox.core import verify_chain
from blackbox.config import load_config


def list_sessions():
    conn = get_conn()
    rows = conn.execute(
        "SELECT session_id, started_at, ended_at, status, total_cost_usd FROM sessions ORDER BY started_at DESC LIMIT 20"
    ).fetchall()
    conn.close()
    if not rows:
        print("No sessions recorded yet in this project.")
        return
    for r in rows:
        cost = r[4] or 0.0
        print(f"{r[0][:12]}  started={r[1]}  ended={r[2]}  status={r[3]}  spend=${cost:.5f}")


def _local_time(iso_ts: str) -> str:
    try:
        dt = datetime.datetime.fromisoformat(iso_ts)
        return dt.astimezone().strftime("%H:%M:%S")
    except (ValueError, TypeError):
        return iso_ts or "??:??:??"


def _try_parse(raw):
    """tool_input is stored as either a JSON string (Claude Code path) or a
    Python dict repr (str(dict) from the LangChain/custom-agent path).
    Try both so humanization works regardless of which source logged it."""
    if not raw:
        return {}
    if isinstance(raw, dict):
        return raw
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        pass
    try:
        parsed = ast.literal_eval(raw)
        return parsed if isinstance(parsed, dict) else {}
    except (ValueError, SyntaxError):
        return {}


_READ_TOOLS = {"Read", "read_file"}
_WRITE_TOOLS = {"Write", "write_file"}
_EDIT_TOOLS = {"Edit", "MultiEdit"}
_BASH_TOOLS = {"Bash", "run_bash"}


def _humanize(row, alerts_enabled: bool):
    """Returns a list of lines (strings) describing one event, formatted
    like: '02:03:14  Read package.json'."""
    _, hook_event, tool_name, tool_input_raw, tool_output_raw, decision = row
    time_str = _local_time(row[0])
    lines = []

    if hook_event == "UserPrompt":
        prompt_text = (tool_output_raw or "").strip()
        if len(prompt_text) > 100:
            prompt_text = prompt_text[:100] + "..."
        lines.append(f'{time_str}  Prompt: "{prompt_text}"')
        return lines

    if hook_event == "ModelUsage":
        parsed = _try_parse(tool_input_raw)
        model = parsed.get("model", "")
        label = f"Called {model} API" if model else "Called LLM API"
        lines.append(f"{time_str}  {label}")
        return lines

    parsed_input = _try_parse(tool_input_raw)
    path = parsed_input.get("file_path") or parsed_input.get("path") or parsed_input.get("notebook_path")
    command = parsed_input.get("command")

    if decision == "block":
        target = command or path or tool_name
        lines.append(f"{time_str}  Agent attempted:")
        lines.append(f"           {target}")
        lines.append(f"           \U0001F6AB BLOCKED")
        if alerts_enabled:
            lines.append(f"{time_str}  Slack alert sent")
        return lines

    if tool_name in _READ_TOOLS:
        lines.append(f"{time_str}  Read {path or '(unknown path)'}")
    elif tool_name in _EDIT_TOOLS:
        lines.append(f"{time_str}  Modified {path or '(unknown path)'}")
    elif tool_name in _WRITE_TOOLS:
        lines.append(f"{time_str}  Wrote {path or '(unknown path)'}")
    elif tool_name in _BASH_TOOLS:
        cmd_display = (command or "").strip()
        if len(cmd_display) > 60:
            cmd_display = cmd_display[:60] + "..."
        lines.append(f"{time_str}  Executed {cmd_display}")
    else:
        lines.append(f"{time_str}  Called {tool_name}")

    return lines


def replay(session_id, raw=False):
    conn = get_conn()
    session_row = conn.execute(
        "SELECT session_id, started_at FROM sessions WHERE session_id LIKE ? LIMIT 1", (session_id + "%",)
    ).fetchone()
    rows = conn.execute(
        "SELECT timestamp, hook_event, tool_name, tool_input, tool_output, decision FROM events "
        "WHERE session_id LIKE ? ORDER BY timestamp ASC",
        (session_id + "%",),
    ).fetchall()
    conn.close()
    if not rows and not session_row:
        print("No session found for that id (try a shorter prefix).")
        return

    if raw:
        for i, r in enumerate(rows, 1):
            print(f"[{i}] {r[0]}  {r[2]}  decision={r[5]}\n    input={r[3][:200]}\n")
        return

    cfg = load_config()
    alerts_enabled = cfg.get("alerts", {}).get("enabled", False)

    full_id = session_row[0] if session_row else session_id
    print(f"SESSION {full_id}")
    if session_row:
        print(f"{_local_time(session_row[1])}  Agent started")

    for row in rows:
        for line in _humanize(row, alerts_enabled):
            print(line)


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
    if not rows:
        print("No flags recorded yet.")
        return
    for r in rows:
        print(f"{r[0]}  [{r[2]}] {r[1]}: {r[3]}")


def stats():
    conn = get_conn()
    row = conn.execute(
        "SELECT COUNT(*), COALESCE(SUM(total_cost_usd), 0) FROM sessions"
    ).fetchone()
    calls = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
    blocked = conn.execute("SELECT COUNT(*) FROM flags WHERE severity = 'block'").fetchone()[0]
    conn.close()
    print(f"Sessions:      {row[0]}")
    print(f"Total spend:   ${row[1]:.5f}")
    print(f"Tool calls:    {calls}")
    print(f"Blocked/flags: {blocked}")


def verify():
    intact, message = verify_chain()
    status = "OK" if intact else "TAMPERING DETECTED"
    print(f"[{status}] {message}")
    if not intact:
        sys.exit(1)


def export(session_id):
    conn = get_conn()
    rows = conn.execute(
        "SELECT event_id, timestamp, hook_event, tool_name, tool_input, tool_output, decision, "
        "cost_usd, row_hash FROM events WHERE session_id LIKE ? ORDER BY timestamp ASC",
        (session_id + "%",),
    ).fetchall()
    flag_rows = conn.execute(
        "SELECT timestamp, rule_name, severity, message FROM flags WHERE session_id LIKE ? ORDER BY timestamp",
        (session_id + "%",),
    ).fetchall()
    conn.close()

    if not rows:
        print("No events found for that session id.")
        return

    filename = f"blackbox_export_{session_id.replace('/', '_')}.csv"
    with open(filename, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["event_id", "timestamp", "hook_event", "tool_name", "tool_input",
                          "tool_output", "decision", "cost_usd", "row_hash"])
        for r in rows:
            writer.writerow(r)
        writer.writerow([])
        writer.writerow(["--- FLAGS ---"])
        writer.writerow(["timestamp", "rule_name", "severity", "message"])
        for r in flag_rows:
            writer.writerow(r)

    print(f"Exported {len(rows)} events and {len(flag_rows)} flags to {filename}")


def report(days=30):
    since = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=days)).isoformat()
    conn = get_conn()
    sessions = conn.execute(
        "SELECT session_id, started_at, ended_at, status, total_cost_usd FROM sessions "
        "WHERE started_at >= ? ORDER BY started_at DESC",
        (since,),
    ).fetchall()
    flag_rows = conn.execute(
        "SELECT session_id, timestamp, rule_name, severity, message FROM flags "
        "WHERE timestamp >= ? ORDER BY timestamp DESC",
        (since,),
    ).fetchall()
    conn.close()

    total_spend = sum(r[4] or 0 for r in sessions)
    blocked_count = sum(1 for r in flag_rows if r[3] == "block")
    warn_count = sum(1 for r in flag_rows if r[3] == "warn")
    intact, chain_msg = verify_chain()

    filename = f"blackbox_report_{datetime.date.today().isoformat()}.md"
    with open(filename, "w") as f:
        f.write(f"# agent-blackbox audit report\n\n")
        f.write(f"Generated: {datetime.datetime.now(datetime.timezone.utc).isoformat()}\n")
        f.write(f"Period: last {days} days\n\n")
        f.write(f"## Summary\n\n")
        f.write(f"- Sessions: {len(sessions)}\n")
        f.write(f"- Total spend: ${total_spend:.4f}\n")
        f.write(f"- Blocked actions: {blocked_count}\n")
        f.write(f"- Warnings: {warn_count}\n")
        f.write(f"- Log integrity: {'INTACT' if intact else 'TAMPERING DETECTED'} — {chain_msg}\n\n")
        f.write(f"## Sessions\n\n")
        f.write("| Session | Started | Status | Spend |\n|---|---|---|---|\n")
        for r in sessions:
            f.write(f"| {r[0][:12]} | {r[1]} | {r[3]} | ${(r[4] or 0):.4f} |\n")
        f.write(f"\n## Flags\n\n")
        if flag_rows:
            f.write("| Time | Session | Rule | Severity | Message |\n|---|---|---|---|---|\n")
            for r in flag_rows:
                f.write(f"| {r[1]} | {r[0][:12]} | {r[2]} | {r[3]} | {r[4]} |\n")
        else:
            f.write("No flags in this period.\n")

    print(f"Wrote {filename}")
    print(f"({len(sessions)} sessions, ${total_spend:.4f} total spend, {blocked_count} blocked, {warn_count} warnings)")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    cmd = sys.argv[1]
    if cmd == "sessions":
        list_sessions()
    elif cmd == "replay" and len(sys.argv) > 2:
        replay(sys.argv[2], raw=("--raw" in sys.argv))
    elif cmd == "flags":
        flags(sys.argv[2] if len(sys.argv) > 2 else None)
    elif cmd == "stats":
        stats()
    elif cmd == "verify":
        verify()
    elif cmd == "export" and len(sys.argv) > 2:
        export(sys.argv[2])
    elif cmd == "report":
        days = 30
        if "--days" in sys.argv:
            idx = sys.argv.index("--days")
            if idx + 1 < len(sys.argv):
                days = int(sys.argv[idx + 1])
        report(days)
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
