# Using Sunyte

A practical walkthrough of Sunyte once it's installed as a Claude Code plugin.
For the "what and why", see [README.md](README.md).

---

## 1. Confirm it's live

Inside any Claude Code session in the project:

```
/sunyte-status
```

You should see your tier, the spend kill switch, and `log integrity : INTACT`.
`/hooks` should list Sunyte on `PreToolUse`, `PostToolUse`, `SessionStart`,
`SessionEnd`, `Stop`, and `UserPromptSubmit`.

Sunyte writes everything to `sunyte.db` (SQLite) and `.sunyte/rules.json` in your
project root. Both are already git-ignored.

---

## 2. Day-to-day: it just runs

Once installed there is nothing to start. Every tool call the agent makes is
checked *before* it runs and logged *after*:

- **Dangerous command** (`rm -rf`, `git push --force`, `DROP TABLE`, …) → the
  agent's tool call is denied and it's told why. It keeps going with other work.
- **Write/read to a protected path** (`.env`, `.git/`, `.ssh/`, `id_rsa`, …) →
  denied.
- **Spend / tool-call / wall-clock limit reached** → every further tool call is
  denied for the rest of the session (the kill switch).
- Everything else → allowed and recorded.

You don't need to do anything for this. The rest of this guide is for when you
want to look at what happened or change what's enforced.

---

## 3. Reviewing a session

| You want to… | Command |
|---|---|
| See recent sessions + spend | `/sunyte-sessions` |
| Replay one frame by frame | `/sunyte-replay <id>` (a short id prefix is fine) |
| See only what was blocked/flagged | `/sunyte-flags` or `/sunyte-flags <id>` |
| Get a plain-English post-mortem | ask Claude: *"use the sunyte-auditor subagent on the last session"* |
| Confirm the log wasn't edited | `/sunyte-verify` |

Same thing from a terminal (no Claude session needed):

```
python3 <plugin>/sunyte/cli.py sessions
python3 <plugin>/sunyte/cli.py replay 1a2b3c
python3 <plugin>/sunyte/cli.py replay 1a2b3c --raw     # per-field dump
python3 <plugin>/sunyte/cli.py flags
python3 <plugin>/sunyte/cli.py stats                   # totals across all sessions
python3 <plugin>/sunyte/cli.py verify
```

`<plugin>` is `~/.claude/plugins/cache/<...>/sunyte@sunyte` — or just run it from
a checkout of this repo. Set `CLAUDE_PROJECT_DIR` to the project whose `sunyte.db`
you want to read if you're not in that directory.

---

## 4. Editing what gets blocked

Built-in defaults are never mutated — your changes are stored as a delta in
`.sunyte/rules.json` and take effect on the **next tool call**, no restart.

```
/sunyte-block                              show every active rule + where it came from
/sunyte-block add "flyctl deploy"          block any command containing this text
/sunyte-block add --regex "rsync .* --delete"
/sunyte-block add --path "infra/prod"      protect a path from writes/reads/deletes
/sunyte-block add --tool "WebFetch"        hard-block a tool by name
/sunyte-block remove "git reset --hard"    turn a rule off (built-in or yours)
/sunyte-block reset                        back to built-in defaults
```

CLI equivalents: `sunyte block list`, `sunyte block add "..."`, etc.

---

## 5. Changing limits and settings

```
/sunyte-config                             show every setting + current value
/sunyte-config set max-spend 10            USD kill switch
/sunyte-config set max-minutes 120
/sunyte-config set max-calls 500
/sunyte-config set warn-pcts 50,80,95      non-blocking budget warnings
/sunyte-config reset [key]
```

Free tier can change limits, retention, and the pricing URL. Slack alerts need
Team; escalation/paging needs Compliance — `/sunyte-config` marks the locked ones.

Prefer YAML in version control? Drop a `config.yaml` in the project root (needs
`pip install pyyaml`). Precedence: `.sunyte/rules.json` → `config.yaml` →
built-in defaults. List fields (`dangerous_bash_patterns`, `protected_paths`, …)
are **added on top of** the built-ins, not replaced.

---

## 6. Tiers / license

```
/sunyte-tier                               show active tier
sunyte tier activate <token>               or set SUNYTE_LICENSE=<token>
```

Team adds full history + cross-session search (`/sunyte-search <text>`), real
dollar cost tracking, CSV/Markdown exports, and Slack alerts. Compliance adds
signed audit manifests and framework mapping (`/sunyte-report --framework soc2`).

---

## 7. Custom / LangChain agents

The same rule engine is callable directly:

```python
from langchain_core.tools import tool
from sunyte.langchain_guard import sunyte_tool, set_current_session
from sunyte.core import start_session

@tool
@sunyte_tool()
def my_tool(x: str) -> str:
    """..."""
    ...

set_current_session(session_id)
start_session(session_id)
```

See [agent_langchain.py](agent_langchain.py) for a full runnable example.

---

## 8. Tests

```
python3 tests/smoke_test.py          # all checks
python3 tests/smoke_test.py -v       # show each assertion
```

The smoke test runs the real rule engine, hash chain, CLI, and `PreToolUse` hook
against an isolated temp project dir — it never touches your real `sunyte.db`.

### Manual end-to-end check in a live session

1. Ask the agent: *"run `git reset --hard HEAD~3`"* → it should be blocked.
2. Ask it to *"read the .env file"* → blocked.
3. Ask it to *"run `ls` and read README.md"* → both allowed.
4. `/sunyte-flags` → the two blocks are listed.
5. `/sunyte-replay <id>` → the blocked attempts appear inline, marked `[BLOCKED]`.
6. `/sunyte-verify` → `INTACT`.
