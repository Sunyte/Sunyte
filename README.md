# Sunyte

**A flight recorder and guardrail layer for AI coding agents.**

Sunyte sits next to your agent, blocks dangerous or out-of-budget actions
*before they run*, logs every tool call to a tamper-evident local log, and gives
you a frame-by-frame replay of any session.

Think of the black box on a plane — but for the thing your agent just did to
your codebase at 2am.

---

## What it does

- **Blocks risky actions before they execute** — dangerous shell commands,
  writes to protected paths (`.env`, `.git/`, `.ssh/`, …), tools outside an
  allowed list, sessions that run too long or spend too much.
- **You own the blocklist.** Add or remove a blocked command yourself with
  `/sunyte-block` — no config spelunking, effective on the very next tool call.
- **Kill switch** on runaway spend, runaway tool-call counts, and runaway
  wall-clock time.
- **Tracks real spend in dollars**, computed from Claude Code's own transcript
  using current Anthropic pricing — not a token guess.
- **Tamper-evident log** — every event is SHA-256 hash-chained to the one
  before it, so any later edit or deletion is detectable with `/sunyte-verify`.
- **Frame-by-frame replay** of any session, after the fact.

It is **local-first and zero-dependency**: the whole engine runs on the Python
standard library. Everything is written to a SQLite file in your project. No
account, no cloud, nothing leaves your machine unless *you* turn on Slack alerts.

---

## Install (Claude Code plugin)

```
/plugin marketplace add Sunyte/Sunyte
/plugin install sunyte@sunyte
```

That's it. The hooks register automatically. Requires `python3` on your `PATH`
(Claude Code already needs it) and a Claude Pro/Max/Team subscription or API
credits.

Verify it's live inside a session with `/sunyte-status`, or `/hooks` to see the
`PreToolUse` / `PostToolUse` / `SessionStart` / `SessionEnd` / `Stop` hooks.

> Prefer not to use the marketplace? Copy `sunyte/`, `hooks/hooks.json` (or the
> repo's `.claude/settings.json`), and optionally `config.yaml` into your
> project. Same behavior.

---

## Slash commands

| Command | What it does |
|---|---|
| `/sunyte-status` | Tier, active guardrails, spend limit, log integrity, at a glance |
| `/sunyte-block` | **Show or edit what gets blocked** (see below) |
| `/sunyte-config` | **Show or change any setting your tier allows** (spend limit, timeouts, alerts…) |
| `/sunyte-sessions` | List recent sessions with spend |
| `/sunyte-replay <id>` | Frame-by-frame replay of one session |
| `/sunyte-flags [id]` | Everything that was flagged or blocked |
| `/sunyte-verify` | Confirm the audit log hasn't been tampered with |
| `/sunyte-tier` | Show the active tier / activate a license |
| `/sunyte-search <text>` | Search every session's prompts + commands *(Team)* |
| `/sunyte-report` | Markdown compliance report *(Team; `--framework` is Compliance)* |

There's also a **`sunyte-auditor`** subagent — ask Claude to "audit the last
Sunyte session" for a read-only post-mortem of an agent run.

---

## Editing the blocklist yourself

The dangerous-command list is yours to change. Built-in defaults are never
touched — your edits are stored as a delta in `.sunyte/rules.json`.

```
/sunyte-block                              show every active rule and where it came from
/sunyte-block add "npm publish"            block any command containing this text
/sunyte-block add --regex "rsync .* --delete"
/sunyte-block add --path "infra/prod"      protect a path from writes/deletes
/sunyte-block add --tool "WebFetch"        hard-block a tool by name
/sunyte-block remove "git reset --hard"    turn a rule off (built-in or yours)
/sunyte-block reset                        back to built-in defaults
```

The same commands work on the CLI: `sunyte block add "npm publish"`,
`sunyte block list`, and so on.

Changes take effect on the **next tool call** — no restart.

---

## Configuration

Defaults ship with the plugin and are sensible out of the box. Change any of
them yourself — no file editing needed:

```
/sunyte-config                                  show every setting + current value
/sunyte-config set max-spend 10                 USD kill switch
/sunyte-config set max-minutes 120
/sunyte-config set max-calls 500
/sunyte-config set warn-pcts 50,80,95
/sunyte-config set slack_webhook_url https://hooks.slack.com/...   (Team tier)
/sunyte-config reset [key]
```

Which settings you can change depends on your tier — `/sunyte-config` marks the
ones locked behind Team or Compliance. Everything is stored in
`.sunyte/rules.json` and applies on the next tool call.

Prefer YAML in version control? Add a `config.yaml` to your project root
(needs `pip install pyyaml`); anything in it overrides a default, and list
fields (`dangerous_bash_patterns`, `protected_paths`, …) are added on top of the
built-ins. Precedence: `.sunyte/rules.json` → `config.yaml` → defaults.

---

## Tiers

| | **Free** | **Team** | **Compliance** |
|---|---|---|---|
| Pre-execution blocking + kill switch | ✅ | ✅ | ✅ |
| Per-session logging + replay | ✅ | ✅ | ✅ |
| Self-edit the blocklist | ✅ | ✅ | ✅ |
| Tamper-evident hash chain + `verify` | ✅ | ✅ | ✅ |
| Full session history + cross-session search | | ✅ | ✅ |
| Real dollar cost tracking, exports (CSV/MD) | | ✅ | ✅ |
| Slack alerts | | ✅ | ✅ |
| Cryptographically signed audit manifests | | | ✅ |
| Framework mapping (SOC 2 / ISO 27001 / NIST 800-53) | | | ✅ |
| Escalation policies (email chains / pager) | | | ✅ |
| SSO, RBAC, org-wide dashboard | | | ✅ (org-managed) |

Activate a license with `sunyte tier activate <token>` (or `SUNYTE_LICENSE`).
Pricing: see the project homepage.

---

## LangChain / custom agents

Sunyte's rule engine is also callable directly, with one decorator:

```python
from langchain_core.tools import tool
from sunyte.langchain_guard import sunyte_tool, set_current_session
from sunyte.core import start_session

@tool
@sunyte_tool()          # <- the entire integration
def my_tool(x: str) -> str:
    """Your existing docstring."""
    ...

set_current_session(session_id)
start_session(session_id)
```

See `agent_langchain.py` for a complete working example (uses Groq's free tier).

---

## How the tamper-evident log works

Each event's hash is `SHA-256(previous_hash + this event's fields)`. Editing or
deleting any past row breaks every hash after it. `sunyte verify` recomputes the
whole chain and tells you either "intact" or exactly which event was altered —
that's what makes the log usable as audit evidence, not just a diary someone
could quietly edit.

---

## Status

Early. Built and tested against Claude Code hooks and against Groq (free tier) +
LangChain. Feedback and bug reports very welcome.

## License

MIT
