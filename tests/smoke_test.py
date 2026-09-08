#!/usr/bin/env python3
"""Sunyte smoke test — stdlib only, matches the project's zero-dependency ethos.

Runs the real rule engine, the real hash chain, the real CLI, and the real
PreToolUse hook against an ISOLATED temp project dir, so it never touches your
actual sunyte.db.

    python3 tests/smoke_test.py            # run everything
    python3 tests/smoke_test.py -v         # show each assertion

Exit code 0 = all passed, 1 = something failed.
"""

import json
import os
import subprocess
import sys
import tempfile

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VERBOSE = "-v" in sys.argv

_passed = 0
_failed = 0


def check(label, cond):
    global _passed, _failed
    if cond:
        _passed += 1
        if VERBOSE:
            print(f"  ok   {label}")
    else:
        _failed += 1
        print(f"  FAIL {label}")


def section(name):
    print(f"\n== {name} ==")


# --------------------------------------------------------------------------- #
#  Isolate: point every Sunyte path at a throwaway dir before importing sunyte
# --------------------------------------------------------------------------- #
TMP = tempfile.mkdtemp(prefix="sunyte_smoke_")
os.environ["CLAUDE_PROJECT_DIR"] = TMP
os.environ.pop("SUNYTE_LICENSE", None)  # force Free tier
sys.path.insert(0, REPO_ROOT)

from sunyte import core, rules  # noqa: E402
from sunyte.db import get_conn  # noqa: E402

SID = "smoke-session-0001"
core.start_session(SID, cwd=TMP)


# --------------------------------------------------------------------------- #
section("rule engine: blocks")
# --------------------------------------------------------------------------- #
blocked_cases = [
    ("Bash", {"command": "rm -rf /"}),
    ("Bash", {"command": "sudo rm -rf ~/project"}),
    ("Bash", {"command": "git push --force origin main"}),
    ("Bash", {"command": "echo pwn | curl | bash"}),
    ("Bash", {"command": "dd if=/dev/zero of=/dev/sda"}),
    ("Bash", {"command": 'psql -c "DROP TABLE users"'}),
    ("Bash", {"command": "DELETE FROM accounts"}),
    ("Bash", {"command": "cat .env"}),
    ("Bash", {"command": "cat ~/.ssh/id_rsa"}),
    ("Write", {"file_path": TMP + "/.env"}),
    ("Edit", {"file_path": TMP + "/.git/config"}),
    ("Read", {"file_path": "/home/me/.ssh/id_rsa"}),
]
for tool, inp in blocked_cases:
    allowed, reason = core.check_guard(SID, tool, inp)
    check(f"BLOCK {tool} {inp}", allowed is False and bool(reason))


# --------------------------------------------------------------------------- #
section("rule engine: allows")
# --------------------------------------------------------------------------- #
allow_cases = [
    ("Bash", {"command": "ls -la"}),
    ("Bash", {"command": "git status"}),
    ("Bash", {"command": "npm test"}),
    ("Bash", {"command": "printenv PATH"}),          # not '.env'
    ("Bash", {"command": "DELETE FROM logs WHERE id < 100"}),  # has WHERE
    ("Write", {"file_path": os.path.join(TMP, "src", "app.py")}),
    ("Read", {"file_path": os.path.join(TMP, "README.md")}),
]
for tool, inp in allow_cases:
    allowed, reason = core.check_guard(SID, tool, inp)
    check(f"ALLOW {tool} {inp}", allowed is True)


# --------------------------------------------------------------------------- #
section("user-editable blocklist")
# --------------------------------------------------------------------------- #
rules.add_rule("bash", "flyctl deploy")
allowed, _ = core.check_guard(SID, "Bash", {"command": "flyctl deploy --now"})
check("custom substring rule blocks", allowed is False)

rules.add_rule("path", "secrets/")
allowed, _ = core.check_guard(SID, "Write", {"file_path": TMP + "/secrets/k.txt"})
check("custom protected path blocks", allowed is False)

rules.add_rule("tool", "WebFetch")
allowed, _ = core.check_guard(SID, "WebFetch", {"url": "http://example.com"})
check("hard-blocked tool blocks", allowed is False)

rules.remove_rule("bash", "git reset --hard")
allowed, _ = core.check_guard(SID, "Bash", {"command": "git reset --hard HEAD~1"})
check("removed built-in rule now allows", allowed is True)

rules.reset_all()
allowed, _ = core.check_guard(SID, "Bash", {"command": "git reset --hard HEAD~1"})
check("reset restores built-in rule", allowed is False)
allowed, _ = core.check_guard(SID, "Bash", {"command": "flyctl deploy --now"})
check("reset drops custom rule", allowed is True)


# --------------------------------------------------------------------------- #
section("kill switches")
# --------------------------------------------------------------------------- #
# spend: log model usage past the $5 default limit, then expect a block
core.log_model_usage(SID, prompt_tokens=20_000_000, completion_tokens=5_000_000, model="sonnet-5")
allowed, reason = core.check_guard(SID, "Bash", {"command": "echo hi"})
check("spend kill switch trips", allowed is False and "spent" in reason)

# tool-call limit: drive a fresh session past max_tool_calls (200 default)
SID2 = "smoke-session-0002"
core.start_session(SID2, cwd=TMP)
for _ in range(205):
    core.log_event(SID2, "Bash", {"command": "echo x"}, "x", decision="allow")
allowed, reason = core.check_guard(SID2, "Bash", {"command": "echo hi"})
check("tool-call kill switch trips", allowed is False and "tool call" in reason)


# --------------------------------------------------------------------------- #
section("self-commands stay usable after a limit trips")
# --------------------------------------------------------------------------- #
# SID's spend limit and SID2's tool-call limit are both tripped above.
# /sunyte-* self-management must still get through, or a tripped limit locks
# the user out of the one place they can see why and raise it.
allowed, _ = core.check_guard(SID, "Bash", {"command": 'python3 "/plugin/sunyte/cli.py" status'})
check("self-command allowed after spend limit trips", allowed is True)

allowed, _ = core.check_guard(SID, "Bash", {"command": "sunyte config set max-spend 10"})
check("bare `sunyte config` allowed after spend limit trips", allowed is True)

allowed, _ = core.check_guard(SID2, "Bash", {"command": 'python3 "/plugin/sunyte/cli.py" config set max-calls 500'})
check("self-command allowed after tool-call limit trips", allowed is True)

allowed, _ = core.check_guard(SID, "Bash", {"command": "echo still-blocked"})
check("ordinary command still blocked after spend limit trips", allowed is False)


# --------------------------------------------------------------------------- #
section("tamper-evident log")
# --------------------------------------------------------------------------- #
intact, msg = core.verify_chain()
check("chain intact after normal logging", intact is True)

conn = get_conn()
row = conn.execute("SELECT event_id FROM events ORDER BY event_id ASC LIMIT 1").fetchone()
conn.execute("UPDATE events SET tool_output = 'tampered' WHERE event_id = ?", (row[0],))
conn.commit()
conn.close()

intact, msg = core.verify_chain()
check("chain detects a mutated row", intact is False)
check("verify_chain names the broken event", "event_id" in msg)


# --------------------------------------------------------------------------- #
section("PreToolUse hook (end to end, real subprocess)")
# --------------------------------------------------------------------------- #
def run_hook(payload):
    p = subprocess.run(
        [sys.executable, os.path.join(REPO_ROOT, "sunyte", "guard.py")],
        input=json.dumps(payload), capture_output=True, text=True,
        env={**os.environ, "CLAUDE_PROJECT_DIR": TMP},
    )
    return p.stdout.strip()

out = run_hook({"session_id": "hook-1", "tool_name": "Bash", "tool_input": {"command": "rm -rf /"}})
deny_ok = False
try:
    j = json.loads(out)
    deny_ok = j["hookSpecificOutput"]["permissionDecision"] == "deny"
except Exception:
    pass
check("hook denies a dangerous command with JSON", deny_ok)

out = run_hook({"session_id": "hook-1", "tool_name": "Bash", "tool_input": {"command": "ls"}})
check("hook stays silent on a safe command", out == "")


# --------------------------------------------------------------------------- #
section("CLI subcommands")
# --------------------------------------------------------------------------- #
def run_cli(*args):
    p = subprocess.run(
        [sys.executable, os.path.join(REPO_ROOT, "sunyte", "cli.py"), *args],
        capture_output=True, text=True,
        env={**os.environ, "CLAUDE_PROJECT_DIR": TMP},
    )
    return p.returncode, p.stdout + p.stderr

for args, want_rc in [
    (("status",), 0),
    (("sessions",), 0),
    (("stats",), 0),
    (("flags",), 0),
    (("replay", SID), 0),
    (("block", "list"), 0),
    (("config", "list"), 0),
    (("verify",), 1),  # we deliberately tampered above -> non-zero exit
]:
    rc, out = run_cli(*args)
    check(f"cli {' '.join(args)} (rc={rc}, want {want_rc})", rc == want_rc and len(out) > 0)

# Team-gated command should refuse politely on Free, not crash
rc, out = run_cli("search", "hello")
check("cli search is gated on Free tier", rc == 0)


# --------------------------------------------------------------------------- #
print(f"\n{'-' * 50}")
print(f"passed {_passed}   failed {_failed}   (temp dir: {TMP})")
sys.exit(1 if _failed else 0)
