"""Core Sunyte logic, callable directly from any agent loop.
This is the same rules/logging engine used by the Claude Code hooks,
just exposed as plain Python functions instead of stdin/JSON scripts."""

import re
import json
import datetime
from sunyte.db import get_conn, get_last_event_hash
from sunyte.config import load_config
from sunyte.alert import send_alert
from sunyte.hashchain import compute_hash

# Tool-name aliases so the same rules apply whether you're on Claude Code
# ("Bash", "Write") or the LangChain/custom-agent path ("run_bash", "write_file").
BASH_TOOL_NAMES = {"Bash", "run_bash"}
FILE_PATH_FIELDS = ["file_path", "path", "notebook_path"]


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


def _insert_event_with_hash(conn, session_id, hook_event, tool_name, tool_input, tool_output, decision, cost_usd=0):
    timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
    tool_input_str = str(tool_input)[:2000]
    tool_output_str = str(tool_output)[:2000]
    prev_hash = get_last_event_hash(conn)
    row_hash = compute_hash(prev_hash, session_id, timestamp, hook_event, tool_name, tool_input_str, tool_output_str, decision)
    conn.execute(
        "INSERT INTO events (session_id, timestamp, hook_event, tool_name, tool_input, tool_output, decision, "
        "cost_usd, prev_hash, row_hash) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (session_id, timestamp, hook_event, tool_name, tool_input_str, tool_output_str, decision,
         cost_usd, prev_hash, row_hash),
    )
    conn.commit()
    return row_hash


def log_event(session_id: str, tool_name: str, tool_input, tool_output, decision: str = "allow"):
    conn = get_conn()
    _insert_event_with_hash(conn, session_id, "ToolCall", tool_name, tool_input, tool_output, decision)
    conn.close()


def log_user_prompt(session_id: str, prompt_text: str):
    """Logs the actual human prompt that triggered a turn/session, so replay
    can show WHY the agent did what it did, not just what it did."""
    conn = get_conn()
    _insert_event_with_hash(conn, session_id, "UserPrompt", "prompt", "", prompt_text, "n/a")
    conn.close()


def log_model_usage(session_id: str, prompt_tokens: int, completion_tokens: int, model: str = "") -> float:
    """Records one LLM call's token usage and cost. Returns the cost of this call in USD."""
    cfg = load_config()
    pricing = cfg.get("pricing", {})
    cost = (
        (prompt_tokens / 1_000_000) * pricing.get("input_per_million_usd", 0)
        + (completion_tokens / 1_000_000) * pricing.get("output_per_million_usd", 0)
    )
    conn = get_conn()
    tool_input = json.dumps({"prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens, "model": model})
    _insert_event_with_hash(conn, session_id, "ModelUsage", "__llm_call__", tool_input, "", "n/a", cost_usd=cost)
    conn.close()
    return cost


def get_session_cost(session_id: str) -> float:
    conn = get_conn()
    total = conn.execute(
        "SELECT COALESCE(SUM(cost_usd), 0) FROM events WHERE session_id = ?", (session_id,)
    ).fetchone()[0]
    conn.close()
    return total or 0.0


def _record_flag(session_id: str, rule_name: str, severity: str, message: str):
    conn = get_conn()
    conn.execute(
        "INSERT INTO flags (session_id, rule_name, severity, message, timestamp) VALUES (?, ?, ?, ?, ?)",
        (session_id, rule_name, severity, message, datetime.datetime.now(datetime.timezone.utc).isoformat()),
    )
    conn.commit()
    conn.close()


def _already_warned(session_id: str, rule_name: str) -> bool:
    conn = get_conn()
    row = conn.execute(
        "SELECT 1 FROM flags WHERE session_id = ? AND rule_name = ? LIMIT 1", (session_id, rule_name)
    ).fetchone()
    conn.close()
    return row is not None


def _get_warning_pcts(cfg) -> list:
    """Reads the multi-tier warning list from config. Falls back to wrapping
    the old single 'spend_warning_pct' value for backward compatibility with
    configs written before this was a list."""
    limits = cfg.get("limits", {})
    if "spend_warning_pcts" in limits:
        return sorted(set(limits["spend_warning_pcts"]))
    if "spend_warning_pct" in limits:
        return [limits["spend_warning_pct"]]
    return [50, 75, 90]


def check_budget_warning(session_id: str, spent: float, max_spend: float, warning_pcts):
    """Fires ONE warning alert per threshold (not a block) as spend crosses
    each configured percentage of the limit. Deduped per-threshold so it
    doesn't re-fire or spam on every subsequent tool call. Accepts either a
    single int (legacy) or a list of ints (multi-tier)."""
    if max_spend <= 0:
        return
    if isinstance(warning_pcts, (int, float)):
        warning_pcts = [warning_pcts]
    for pct in warning_pcts:
        if pct <= 0:
            continue
        threshold = max_spend * (pct / 100.0)
        rule_name = f"budget_warning_{pct}pct"
        if spent >= threshold and not _already_warned(session_id, rule_name):
            msg = f"Session has spent ${spent:.4f}, crossing {pct}% of the ${max_spend:.2f} limit."
            _record_flag(session_id, rule_name, "warn", msg)
            send_alert(f"Budget warning: session {session_id[:8]} is at {pct}% of its spend limit (${spent:.4f} of ${max_spend:.2f}).")


def check_spend_limit(session_id: str):
    """Returns (ok: bool, reason: str). Call this before running the next tool call."""
    cfg = load_config()
    limits = cfg.get("limits", {})
    max_spend = limits.get("max_spend_usd", 0.50)
    warning_pcts = _get_warning_pcts(cfg)
    spent = get_session_cost(session_id)

    check_budget_warning(session_id, spent, max_spend, warning_pcts)

    if spent >= max_spend:
        msg = f"Session has spent ${spent:.4f}, exceeding limit of ${max_spend:.2f}."
        _record_flag(session_id, "max_spend", "block", msg)
        send_alert(f"Session {session_id[:8]} hit its spend limit (${spent:.4f}) and was stopped.")
        return False, msg
    return True, ""


def _touches_protected_path(protected: str, command: str) -> bool:
    """Boundary-aware check for a protected path inside a raw shell command.

    Plain substring matching is too eager here: `.env` would match inside
    `os.environ`, `printenv`, etc. We require the token to sit at a path-ish
    boundary - not glued to a preceding word character or dot, and (unless the
    token itself ends in `/`) not glued to a following word character.
    """
    token = re.escape(protected.lower())
    trailing = "" if protected.endswith(("/", "\\")) else r"(?![A-Za-z0-9])"
    pattern = r"(?<![A-Za-z0-9.])" + token + trailing
    try:
        return re.search(pattern, command.lower()) is not None
    except re.error:
        return protected.lower() in command.lower()


def _extract_path(tool_input: dict):
    for field in FILE_PATH_FIELDS:
        if field in tool_input:
            return str(tool_input[field])
    return None


def _deny(session_id, tool_name, tool_input, msg, rule_name, alert_msg):
    """Shared denial path: records the flag, logs the ATTEMPT itself into the
    events table (so it shows up inline in replay, not just in `flags`),
    sends the alert, and returns the (False, reason) tuple."""
    _record_flag(session_id, rule_name, "block", msg)
    log_event(session_id, tool_name, tool_input, f"BLOCKED: {msg}", decision="block")
    send_alert(alert_msg, severity="block")
    return False, msg


def check_guard(session_id: str, tool_name: str, tool_input: dict):
    """Returns (allowed: bool, reason: str). Call this BEFORE running a tool.
    This is the single shared rule engine used by both the Claude Code hooks
    and the LangChain/custom-agent integration."""
    cfg = load_config()

    # Rule 1: hard-blocked tools
    if tool_name in cfg.get("blocked_tools", []):
        msg = f"Tool '{tool_name}' is on the hard-blocked list."
        return _deny(session_id, tool_name, tool_input, msg, "blocked_tool",
                     f"Blocked tool call `{tool_name}` in session {session_id[:8]}.")

    # Rule 2: dangerous Bash patterns (substring) + regex patterns
    if tool_name in BASH_TOOL_NAMES:
        command = tool_input.get("command", "")
        for pattern in cfg.get("dangerous_bash_patterns", []):
            if pattern.lower() in command.lower():
                msg = f"Command matched dangerous pattern: '{pattern}'"
                return _deny(session_id, tool_name, tool_input, msg, "dangerous_bash",
                             f"Blocked dangerous command in session {session_id[:8]}: `{command[:100]}`")
        for regex in cfg.get("dangerous_regex_patterns", []):
            try:
                if re.search(regex, command, re.IGNORECASE):
                    msg = f"Command matched dangerous pattern (regex): '{regex}'"
                    return _deny(session_id, tool_name, tool_input, msg, "dangerous_bash_regex",
                                 f"Blocked dangerous command in session {session_id[:8]}: `{command[:100]}`")
            except re.error:
                continue  # a malformed regex in config shouldn't crash the guard

        # Rule 2b: protected paths, checked as a substring against the raw command too
        # (covers things like `cat .env` or `rm .ssh/id_rsa` that aren't in file-path fields)
        for protected in cfg.get("protected_paths", []):
            if _touches_protected_path(protected, command):
                msg = f"Command touches a protected path: '{protected}'"
                return _deny(session_id, tool_name, tool_input, msg, "protected_path",
                             f"Blocked command touching protected path in session {session_id[:8]}: `{command[:100]}`")

    # Rule 3: path-based guardrails for file tools (Write/Edit/Read/write_file/read_file/...)
    path = _extract_path(tool_input)
    if path:
        for protected in cfg.get("protected_paths", []):
            if protected.lower() in path.lower():
                msg = f"Path '{path}' matches protected path pattern: '{protected}'"
                return _deny(session_id, tool_name, tool_input, msg, "protected_path",
                             f"Blocked file access to protected path in session {session_id[:8]}: `{path}`")

    # Rule 4: spend limit (block) + multi-tier budget warnings (non-blocking, fire once each)
    limits = cfg.get("limits", {})
    max_spend = limits.get("max_spend_usd", 0.50)
    warning_pcts = _get_warning_pcts(cfg)
    spent = get_session_cost(session_id)
    check_budget_warning(session_id, spent, max_spend, warning_pcts)
    if spent >= max_spend:
        msg = f"Session has spent ${spent:.4f}, exceeding limit of ${max_spend:.2f}."
        return _deny(session_id, tool_name, tool_input, msg, "max_spend",
                     f"Session {session_id[:8]} hit its spend limit (${spent:.4f}) and was stopped.")

    # Rule 5: too many tool calls this session
    conn = get_conn()
    count = conn.execute("SELECT COUNT(*) FROM events WHERE session_id = ?", (session_id,)).fetchone()[0]
    max_calls = limits.get("max_tool_calls", 200)
    if count >= max_calls:
        conn.close()
        msg = f"Session has made {count} tool calls, exceeding limit of {max_calls}."
        return _deny(session_id, tool_name, tool_input, msg, "max_tool_calls",
                     f"Session {session_id[:8]} hit the tool-call limit ({count}) and was stopped.")

    # Rule 6: session running too long
    row = conn.execute("SELECT started_at FROM sessions WHERE session_id = ?", (session_id,)).fetchone()
    conn.close()
    if row:
        started_at = datetime.datetime.fromisoformat(row[0])
        elapsed_minutes = (datetime.datetime.now(datetime.timezone.utc) - started_at).total_seconds() / 60
        max_minutes = limits.get("max_session_minutes", 30)
        if elapsed_minutes >= max_minutes:
            msg = f"Session has run {elapsed_minutes:.1f} min, exceeding limit of {max_minutes} min."
            return _deny(session_id, tool_name, tool_input, msg, "max_session_time",
                         f"Session {session_id[:8]} exceeded time limit and was stopped.")

    # Rule 7: off-path tool (warn only, don't block)
    allowed = cfg.get("allowed_tools", [])
    if allowed and tool_name not in allowed:
        msg = f"Tool '{tool_name}' is outside the normal allowed set."
        _record_flag(session_id, "off_path_tool", "warn", msg)
        send_alert(f"Off-path tool `{tool_name}` used in session {session_id[:8]} (allowed, just flagged).")

    return True, ""


def verify_chain():
    """Recomputes the entire event hash chain from scratch. Returns (intact: bool, message: str)."""
    conn = get_conn()
    rows = conn.execute(
        "SELECT event_id, session_id, timestamp, hook_event, tool_name, tool_input, tool_output, "
        "decision, prev_hash, row_hash FROM events ORDER BY event_id ASC"
    ).fetchall()
    conn.close()

    expected_prev = ""
    for row in rows:
        (event_id, session_id, timestamp, hook_event, tool_name, tool_input,
         tool_output, decision, stored_prev, stored_hash) = row

        if stored_prev != expected_prev:
            return False, f"Chain broken at event_id={event_id}: prev_hash doesn't match the prior row's hash."

        recomputed = compute_hash(stored_prev, session_id, timestamp, hook_event, tool_name, tool_input, tool_output, decision)
        if recomputed != stored_hash:
            return False, f"Chain broken at event_id={event_id}: stored hash doesn't match recomputed hash (row was likely edited)."

        expected_prev = stored_hash

    return True, f"Chain intact. {len(rows)} events verified."
