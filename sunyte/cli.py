#!/usr/bin/env python3
"""Sunyte CLI.

  sunyte sessions                    list recent sessions
  sunyte replay <session_id>         human-readable timeline replay
  sunyte replay <session_id> --raw   raw per-field dump
  sunyte flags [session_id]          flagged / blocked events
  sunyte stats                       totals across all sessions
  sunyte status                      tier + config + integrity at a glance
  sunyte verify                      check the tamper-evident hash chain
  sunyte block ...                   view / edit what gets blocked (see below)
  sunyte config ...                  view / change any setting your tier allows
  sunyte tier ...                    show or activate a Team / Compliance license

  sunyte config list
  sunyte config set max-spend 10           dollars (kill switch)
  sunyte config set max-minutes 120
  sunyte config set warn-pcts 50,80,95
  sunyte config set slack_webhook_url https://hooks.slack.com/...   (Team)
  sunyte config reset [key]

  Team tier:
  sunyte search <text>               search every session's prompts + commands
  sunyte export <session_id>         one session's full audit trail as CSV
  sunyte report [--days N]           Markdown compliance summary

  Compliance tier:
  sunyte sign [--days N]             signed, verifiable audit manifest
  sunyte report --framework <name>   report mapped to a compliance framework

  sunyte block list
  sunyte block add "<pattern>"              add a blocked command substring
  sunyte block add --regex "<pattern>"      add a blocked-command regex
  sunyte block add --path "<pattern>"       add a protected path
  sunyte block add --tool "<ToolName>"      hard-block a tool outright
  sunyte block remove "<pattern>"           remove any rule by its text
  sunyte block reset [--type bash|regex|path|tool]   back to built-in defaults
"""
import os
import sys
import csv
import json
import ast
import hashlib
import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:  # keep output legible on legacy Windows code pages
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):
    pass

from sunyte.db import get_conn
from sunyte.core import verify_chain
from sunyte.config import load_config
from sunyte import tier as tiers


# --------------------------------------------------------------------------- #
#  Free tier
# --------------------------------------------------------------------------- #

def list_sessions():
    cfg = load_config()
    limit = cfg.get("retention", {}).get("free_sessions_listed", 10)
    unlimited = tiers.at_least("team")

    conn = get_conn()
    total = conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
    rows = conn.execute(
        "SELECT session_id, started_at, ended_at, status, total_cost_usd FROM sessions "
        "ORDER BY started_at DESC" + ("" if unlimited else f" LIMIT {int(limit)}")
    ).fetchall()
    conn.close()

    if not rows:
        print("No sessions recorded yet in this project.")
        return
    for r in rows:
        cost = r[4] or 0.0
        print(f"{r[0][:12]}  started={r[1]}  ended={r[2]}  status={r[3]}  spend=${cost:.5f}")

    if not unlimited and total > len(rows):
        print(f"\n... {total - len(rows)} older session(s) hidden on the Free tier "
              f"(still replayable by id).\n    Upgrade to Team for full history + search: {tiers.upgrade_url()}")


def _local_time(iso_ts: str) -> str:
    try:
        return datetime.datetime.fromisoformat(iso_ts).astimezone().strftime("%H:%M:%S")
    except (ValueError, TypeError):
        return iso_ts or "??:??:??"


def _try_parse(raw):
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
        lines.append(f"{time_str}  {'Called ' + model + ' API' if model else 'Called LLM API'}")
        return lines

    parsed_input = _try_parse(tool_input_raw)
    path = parsed_input.get("file_path") or parsed_input.get("path") or parsed_input.get("notebook_path")
    command = parsed_input.get("command")

    if decision == "block":
        target = command or path or tool_name
        lines.append(f"{time_str}  Agent attempted:")
        lines.append(f"           {target}")
        lines.append(f"           [BLOCKED]")
        if alerts_enabled:
            lines.append(f"{time_str}  Alert sent")
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
    alerts_enabled = bool(cfg.get("alerts", {}).get("enabled", False)) and tiers.at_least("team")

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
    row = conn.execute("SELECT COUNT(*), COALESCE(SUM(total_cost_usd), 0) FROM sessions").fetchone()
    calls = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
    blocked = conn.execute("SELECT COUNT(*) FROM flags WHERE severity = 'block'").fetchone()[0]
    conn.close()
    print(f"Sessions:      {row[0]}")
    print(f"Total spend:   ${row[1]:.5f}")
    print(f"Tool calls:    {calls}")
    print(f"Blocked/flags: {blocked}")


def status():
    cfg = load_config()
    tier = tiers.get_tier()
    intact, chain_msg = verify_chain()
    conn = get_conn()
    sess = conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
    blocked = conn.execute("SELECT COUNT(*) FROM flags WHERE severity = 'block'").fetchone()[0]
    conn.close()

    print(f"Sunyte - tier: {tier.upper()}")
    print(f"  sessions recorded : {sess}")
    print(f"  hard blocks       : {blocked}")
    print(f"  log integrity     : {'INTACT' if intact else 'TAMPERING DETECTED'}")
    print(f"  spend kill switch : ${cfg['limits'].get('max_spend_usd')}  "
          f"(warn at {cfg['limits'].get('spend_warning_pcts')}%)")
    print(f"  blocked commands  : {len(cfg.get('dangerous_bash_patterns', []))} substring + "
          f"{len(cfg.get('dangerous_regex_patterns', []))} regex")
    print(f"  protected paths   : {len(cfg.get('protected_paths', []))}")
    print(f"  alerts            : {'on' if cfg.get('alerts', {}).get('enabled') else 'off'}"
          f"{'' if tiers.at_least('team') else '  (Team tier)'}")
    if tier == "free":
        print(f"\n  Team & Compliance features: {tiers.upgrade_url()}")


def verify():
    intact, message = verify_chain()
    print(f"[{'OK' if intact else 'TAMPERING DETECTED'}] {message}")
    if not intact:
        sys.exit(1)


# --------------------------------------------------------------------------- #
#  Blocklist editing (Free tier)
# --------------------------------------------------------------------------- #

def block(args):
    from sunyte import rules

    if not args or args[0] in ("list", "show"):
        print("Active Sunyte rules:")
        print(rules.describe())
        return

    action = args[0]
    rest = args[1:]

    field = None
    for flag, name in (("--regex", "regex"), ("--path", "path"),
                       ("--tool", "tool"), ("--bash", "bash"), ("--allow-tool", "allow-tool")):
        if flag in rest:
            field = name
            rest = [a for a in rest if a != flag]
    if "--type" in rest:
        i = rest.index("--type")
        field = rest[i + 1] if i + 1 < len(rest) else field
        rest = rest[:i] + rest[i + 2:]

    pattern = " ".join(rest).strip().strip('"').strip("'")

    try:
        if action == "add":
            print(rules.add_rule(field or "bash", pattern))
        elif action in ("remove", "rm", "delete"):
            print(rules.remove_rule(field, pattern) if field else rules.remove_any(pattern))
        elif action == "reset":
            print(rules.reset_field(field) if field else rules.reset_all())
        else:
            print(f"Unknown 'block' action: {action}")
            print(__doc__)
    except ValueError as e:
        print(f"Error: {e}")
        sys.exit(1)


def config(args):
    from sunyte import settings

    if not args or args[0] in ("list", "show"):
        print(settings.describe())
        return
    action = args[0]
    try:
        if action == "set" and len(args) >= 3:
            print(settings.set_setting(args[1], " ".join(args[2:])))
        elif action == "set" and len(args) == 2 and "=" in args[1]:
            key, val = args[1].split("=", 1)
            print(settings.set_setting(key, val))
        elif action == "reset":
            print(settings.reset_setting(args[1] if len(args) > 1 else None))
        else:
            print("Usage: sunyte config [list | set <key> <value> | reset [key]]")
            print(settings.describe())
    except ValueError as e:
        print(f"Error: {e}")
        sys.exit(1)


# --------------------------------------------------------------------------- #
#  Tier / license
# --------------------------------------------------------------------------- #

def tier(args):
    if not args or args[0] == "show":
        print(f"Current tier: {tiers.get_tier().upper()}")
        print(f"Pricing & upgrade: {tiers.upgrade_url()}")
        return
    if args[0] in ("activate", "set") and len(args) > 1:
        try:
            new_tier = tiers.activate(args[1])
            print(f"Activated. Tier is now {new_tier.upper()}.")
        except ValueError as e:
            print(f"Error: {e}")
            sys.exit(1)
        return
    if args[0] == "issue" and len(args) > 1:
        try:
            print(tiers.issue_token(args[1]))
        except ValueError as e:
            print(f"Error: {e}")
            sys.exit(1)
        return
    print("Usage: sunyte tier [show | activate <token> | issue <tier>]")


# --------------------------------------------------------------------------- #
#  Team tier
# --------------------------------------------------------------------------- #

def search(text):
    if not tiers.gate("team", "Cross-session search"):
        return
    like = f"%{text}%"
    conn = get_conn()
    rows = conn.execute(
        "SELECT session_id, timestamp, hook_event, tool_name, tool_input, tool_output, decision "
        "FROM events WHERE tool_input LIKE ? OR tool_output LIKE ? ORDER BY timestamp DESC LIMIT 100",
        (like, like),
    ).fetchall()
    conn.close()
    if not rows:
        print(f"No events matching '{text}'.")
        return
    for r in rows:
        blob = (r[4] or "") + " " + (r[5] or "")
        snippet = blob.strip().replace("\n", " ")
        if len(snippet) > 120:
            snippet = snippet[:120] + "..."
        mark = " [BLOCKED]" if r[6] == "block" else ""
        print(f"{r[0][:12]}  {r[1]}  {r[2]}/{r[3]}{mark}\n    {snippet}\n")


def export(session_id):
    if not tiers.gate("team", "CSV export"):
        return
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
    filename = f"sunyte_export_{session_id.replace('/', '_')}.csv"
    with open(filename, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["event_id", "timestamp", "hook_event", "tool_name", "tool_input",
                         "tool_output", "decision", "cost_usd", "row_hash"])
        writer.writerows(rows)
        writer.writerow([])
        writer.writerow(["--- FLAGS ---"])
        writer.writerow(["timestamp", "rule_name", "severity", "message"])
        writer.writerows(flag_rows)
    print(f"Exported {len(rows)} events and {len(flag_rows)} flags to {filename}")


def report(days=30, framework=None):
    if not tiers.gate("team", "Compliance reporting"):
        return
    if framework and not tiers.gate("compliance", f"Framework mapping ({framework})"):
        return

    since = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=days)).isoformat()
    conn = get_conn()
    sessions = conn.execute(
        "SELECT session_id, started_at, ended_at, status, total_cost_usd FROM sessions "
        "WHERE started_at >= ? ORDER BY started_at DESC", (since,),
    ).fetchall()
    flag_rows = conn.execute(
        "SELECT session_id, timestamp, rule_name, severity, message FROM flags "
        "WHERE timestamp >= ? ORDER BY timestamp DESC", (since,),
    ).fetchall()
    conn.close()

    total_spend = sum(r[4] or 0 for r in sessions)
    blocked_count = sum(1 for r in flag_rows if r[3] == "block")
    warn_count = sum(1 for r in flag_rows if r[3] == "warn")
    intact, chain_msg = verify_chain()

    filename = f"sunyte_report_{datetime.date.today().isoformat()}.md"
    with open(filename, "w", encoding="utf-8") as f:
        f.write("# Sunyte audit report\n\n")
        f.write(f"Generated: {datetime.datetime.now(datetime.timezone.utc).isoformat()}\n")
        f.write(f"Period: last {days} days\n")
        f.write(f"Tier: {tiers.get_tier().capitalize()}\n\n")
        f.write("## Summary\n\n")
        f.write(f"- Sessions: {len(sessions)}\n")
        f.write(f"- Total spend: ${total_spend:.4f}\n")
        f.write(f"- Blocked actions: {blocked_count}\n")
        f.write(f"- Warnings: {warn_count}\n")
        f.write(f"- Log integrity: {'INTACT' if intact else 'TAMPERING DETECTED'} - {chain_msg}\n\n")
        if framework:
            f.write(_framework_section(framework, blocked_count, intact))
        f.write("## Sessions\n\n| Session | Started | Status | Spend |\n|---|---|---|---|\n")
        for r in sessions:
            f.write(f"| {r[0][:12]} | {r[1]} | {r[3]} | ${(r[4] or 0):.4f} |\n")
        f.write("\n## Flags\n\n")
        if flag_rows:
            f.write("| Time | Session | Rule | Severity | Message |\n|---|---|---|---|---|\n")
            for r in flag_rows:
                f.write(f"| {r[1]} | {r[0][:12]} | {r[2]} | {r[3]} | {r[4]} |\n")
        else:
            f.write("No flags in this period.\n")
    print(f"Wrote {filename}")
    print(f"({len(sessions)} sessions, ${total_spend:.4f} spend, {blocked_count} blocked, {warn_count} warnings)")


_FRAMEWORKS = {
    "soc2": [
        ("CC7.2", "Detect and respond to anomalies", "PreToolUse guard blocks + flag records"),
        ("CC7.3", "Evaluate security events", "tamper-evident event log + `sunyte verify`"),
        ("CC6.1", "Restrict privileged actions", "dangerous-command + protected-path blocklist"),
    ],
    "iso27001": [
        ("A.8.16", "Monitoring activities", "every tool call logged with timestamp + hash chain"),
        ("A.8.15", "Logging", "append-only hash-chained event log"),
        ("A.5.25", "Assessment of security events", "flags table + escalation policy"),
    ],
    "nist80053": [
        ("AU-10", "Non-repudiation", "SHA-256 hash chain per event"),
        ("SI-4", "System monitoring", "PreToolUse / PostToolUse hooks on every action"),
        ("AC-6", "Least privilege", "allowed_tools + blocked_tools enforcement"),
    ],
}


def _framework_section(framework, blocked_count, intact):
    key = framework.lower().replace("-", "").replace(" ", "")
    controls = _FRAMEWORKS.get(key)
    out = [f"## Control mapping - {framework}\n\n"]
    if not controls:
        out.append(f"No built-in mapping for '{framework}'. Known: {', '.join(_FRAMEWORKS)}.\n\n")
        return "".join(out)
    out.append("| Control | Objective | How Sunyte addresses it |\n|---|---|---|\n")
    for cid, obj, how in controls:
        out.append(f"| {cid} | {obj} | {how} |\n")
    out.append(f"\nEvidence this period: {blocked_count} enforced blocks, "
               f"log integrity {'verified' if intact else 'FAILED'}.\n\n")
    return "".join(out)


# --------------------------------------------------------------------------- #
#  Compliance tier
# --------------------------------------------------------------------------- #

def sign(days=30):
    if not tiers.gate("compliance", "Signed audit manifests"):
        return
    intact, chain_msg = verify_chain()
    conn = get_conn()
    row = conn.execute(
        "SELECT COUNT(*), MIN(timestamp), MAX(timestamp), "
        "(SELECT row_hash FROM events ORDER BY event_id DESC LIMIT 1) FROM events"
    ).fetchone()
    conn.close()

    manifest = {
        "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "tool": "sunyte",
        "tier": tiers.get_tier(),
        "events": row[0],
        "first_event": row[1],
        "last_event": row[2],
        "chain_head_hash": row[3] or "",
        "chain_intact": intact,
        "chain_message": chain_msg,
    }
    body = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode("utf-8")
    # Scaffold signature. Swap for an org-held asymmetric key (e.g. `cosign`,
    # an HSM, or Sigstore) — the manifest body is already canonical JSON.
    manifest["signature_alg"] = "sha256-scaffold"
    manifest["signature"] = hashlib.sha256(b"sunyte-sign-v1|" + body).hexdigest()

    filename = f"sunyte_manifest_{datetime.date.today().isoformat()}.json"
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)
    print(f"Wrote {filename}  (chain {'INTACT' if intact else 'BROKEN'}, {row[0]} events)")


# --------------------------------------------------------------------------- #

def _arg_after(flag, default):
    if flag in sys.argv:
        i = sys.argv.index(flag)
        if i + 1 < len(sys.argv):
            return sys.argv[i + 1]
    return default


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
        flags(sys.argv[2] if len(sys.argv) > 2 and not sys.argv[2].startswith("-") else None)
    elif cmd == "stats":
        stats()
    elif cmd == "status":
        status()
    elif cmd == "verify":
        verify()
    elif cmd == "block":
        block(sys.argv[2:])
    elif cmd in ("config", "limit"):
        config(sys.argv[2:])
    elif cmd == "tier":
        tier(sys.argv[2:])
    elif cmd == "search" and len(sys.argv) > 2:
        search(" ".join(a for a in sys.argv[2:] if not a.startswith("-")))
    elif cmd == "export" and len(sys.argv) > 2:
        export(sys.argv[2])
    elif cmd == "report":
        report(int(_arg_after("--days", 30)), framework=_arg_after("--framework", None))
    elif cmd == "sign":
        sign(int(_arg_after("--days", 30)))
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
