"""Core black-box logic, callable directly from any agent loop.
This is the same rules/logging engine used by the Claude Code hooks,
just exposed as plain Python functions instead of stdin/JSON scripts."""

import datetime
from blackbox.db import get_conn
from blackbox.config import load_config
from blackbox.alert import send_alert


def start_session(session_id: str, cwd: str = ""):
    conn = get_conn()
    conn.execute(
        "INSERT OR IGNORE INTO sessions (session_id, started_at, cwd, status) VALUES (?, ?, ?, 'running')",
        (session_id, datetime.datetime.now(datetime.timezone.utc).isoformat(), cwd),
    )
    conn.commit()
    conn.close()


def end_session(session_id: str):
    conn = get_conn()
    totals = conn.execute(
        "SELECT COALESCE(SUM(cost_usd), 0), "
        "COALESCE(SUM(CAST(json_extract(tool_input, '$.prompt_tokens') AS INTEGER)), 0), "
        "COALESCE(SUM(CAST(json_extract(tool_input, '$.completion_tokens') AS INTEGER)), 0) "
        "FROM events WHERE session_id = ? AND hook_event = 'ModelUsage'",
        (session_id,),
    ).fetchone()
    total_cost, total_in, total_out = totals
    conn.execute(
        "UPDATE sessions SET ended_at = ?, status = 'completed', total_cost_usd = ?, "
        "total_input_tokens = ?, total_output_tokens = ? WHERE session_id = ?",
        (datetime.datetime.now(datetime.timezone.utc).isoformat(), total_cost, total_in, total_out, session_id),
    )
    conn.commit()
    conn.close()


def log_event(session_id: str, tool_name: str, tool_input: str, tool_output: str, decision: str = "allow"):
    conn = get_conn()
    conn.execute(
        "INSERT INTO events (session_id, timestamp, hook_event, tool_name, tool_input, tool_output, decision) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (session_id, datetime.datetime.now(datetime.timezone.utc).isoformat(), "ToolCall",
         tool_name, str(tool_input)[:2000], str(tool_output)[:2000], decision),
    )
    conn.commit()
    conn.close()


def log_model_usage(session_id: str, prompt_tokens: int, completion_tokens: int) -> float:
    """Records one LLM call's token usage and cost. Returns the cost of this call in USD."""
    cfg = load_config()
    pricing = cfg.get("pricing", {})
    cost = (
        (prompt_tokens / 1_000_000) * pricing.get("input_per_million_usd", 0)
        + (completion_tokens / 1_000_000) * pricing.get("output_per_million_usd", 0)
    )
    conn = get_conn()
    conn.execute(
        "INSERT INTO events (session_id, timestamp, hook_event, tool_name, tool_input, tool_output, decision, cost_usd) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (session_id, datetime.datetime.now(datetime.timezone.utc).isoformat(), "ModelUsage", "__llm_call__",
         f'{{"prompt_tokens": {prompt_tokens}, "completion_tokens": {completion_tokens}}}', "", "n/a", cost),
    )
    conn.commit()
    conn.close()
    return cost


def get_session_cost(session_id: str) -> float:
    conn = get_conn()
    total = conn.execute(
        "SELECT COALESCE(SUM(cost_usd), 0) FROM events WHERE session_id = ?", (session_id,)
    ).fetchone()[0]
    conn.close()
    return total or 0.0


def check_spend_limit(session_id: str):
    """Returns (ok: bool, reason: str). Call this before running the next tool call."""
    cfg = load_config()
    max_spend = cfg.get("limits", {}).get("max_spend_usd", 0.50)
    spent = get_session_cost(session_id)
    if spent >= max_spend:
        msg = f"Session has spent ${spent:.4f}, exceeding limit of ${max_spend:.2f}."
        _record_flag(session_id, "max_spend", "block", msg)
        send_alert(f"Session {session_id[:8]} hit its spend limit (${spent:.4f}) and was stopped.")
        return False, msg
    return True, ""


def _record_flag(session_id: str, rule_name: str, severity: str, message: str):
    conn = get_conn()
    conn.execute(
        "INSERT INTO flags (session_id, rule_name, severity, message, timestamp) VALUES (?, ?, ?, ?, ?)",
        (session_id, rule_name, severity, message, datetime.datetime.now(datetime.timezone.utc).isoformat()),
    )
    conn.commit()
    conn.close()


def check_guard(session_id: str, tool_name: str, tool_input: dict):
    """Returns (allowed: bool, reason: str). Call this BEFORE running a tool."""
    cfg = load_config()

    # Rule 1: hard-blocked tools
    if tool_name in cfg.get("blocked_tools", []):
        msg = f"Tool '{tool_name}' is on the hard-blocked list."
        _record_flag(session_id, "blocked_tool", "block", msg)
        send_alert(f"Blocked tool call `{tool_name}` in session {session_id[:8]}.")
        return False, msg

    # Rule 2: dangerous Bash patterns
    if tool_name == "run_bash":
        command = tool_input.get("command", "")
        for pattern in cfg.get("dangerous_bash_patterns", []):
            if pattern in command:
                msg = f"Command matched dangerous pattern: '{pattern}'"
                _record_flag(session_id, "dangerous_bash", "block", msg)
                send_alert(f"Blocked dangerous command in session {session_id[:8]}: `{command[:100]}`")
                return False, msg

    # Rule 3: too many tool calls this session
    conn = get_conn()
    count = conn.execute("SELECT COUNT(*) FROM events WHERE session_id = ?", (session_id,)).fetchone()[0]
    max_calls = cfg.get("limits", {}).get("max_tool_calls", 200)
    if count >= max_calls:
        msg = f"Session has made {count} tool calls, exceeding limit of {max_calls}."
        _record_flag(session_id, "max_tool_calls", "block", msg)
        send_alert(f"Session {session_id[:8]} hit the tool-call limit ({count}) and was stopped.")
        conn.close()
        return False, msg

    # Rule 4: session running too long
    row = conn.execute("SELECT started_at FROM sessions WHERE session_id = ?", (session_id,)).fetchone()
    conn.close()
    if row:
        started_at = datetime.datetime.fromisoformat(row[0])
        elapsed_minutes = (datetime.datetime.now(datetime.timezone.utc) - started_at).total_seconds() / 60
        max_minutes = cfg.get("limits", {}).get("max_session_minutes", 30)
        if elapsed_minutes >= max_minutes:
            msg = f"Session has run {elapsed_minutes:.1f} min, exceeding limit of {max_minutes} min."
            _record_flag(session_id, "max_session_time", "block", msg)
            send_alert(f"Session {session_id[:8]} exceeded time limit and was stopped.")
            return False, msg

    # Rule 5: off-path tool (warn only, don't block)
    allowed = cfg.get("allowed_tools", [])
    if allowed and tool_name not in allowed:
        msg = f"Tool '{tool_name}' is outside the normal allowed set."
        _record_flag(session_id, "off_path_tool", "warn", msg)
        send_alert(f"Off-path tool `{tool_name}` used in session {session_id[:8]} (allowed, just flagged).")

    return True, ""
