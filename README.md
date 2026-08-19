# agent-blackbox

A black box recorder for AI agents. It sits next to your agent, logs every tool
call, blocks dangerous or out-of-budget actions before they run, and gives you
a frame-by-frame replay of any session.

Think flight recorder for planes, but for the thing your agent just did to
your codebase at 2am.

## What it actually does

- **Logs every tool call** your agent makes — what it ran, what it touched, when
- **Blocks risky actions before they execute** — dangerous shell commands, writes
  to protected paths, tools outside an allowed list, sessions that run too long
  or spend too much
- **Tracks real spend in dollars**, not just token counts, with warnings before
  the hard limit hits
- **Tamper-evident logs** — every event is hash-chained to the one before it, so
  any edit or deletion after the fact is detectable
- **Alerts you on Slack** the moment something gets flagged or blocked
- **Replays any session** step by step after the fact
- **Exports audit reports** (CSV per-session, Markdown compliance summaries)

It's local-first: everything is logged to a SQLite file in your project. No
account, no cloud dashboard, no data leaving your machine unless you turn on
Slack alerts yourself.

## Install

```bash
pip install -e ".[langchain]"   # if you're using LangChain agents
# or
pip install -e ".[groq]"        # if you're calling Groq directly
```

(This installs from a local clone for now — not yet published to PyPI.)

## Quickstart: LangChain

If you already have LangChain tools, the entire integration is one decorator
and one function call:

```python
from langchain_core.tools import tool
from blackbox.langchain_guard import black_box_tool, set_current_session
from blackbox.langchain_handler import BlackBoxCallbackHandler
from blackbox.core import start_session

@tool
@black_box_tool()          # <- add this line to any existing tool
def my_tool(x: str) -> str:
    """Your existing docstring."""
    ...

session_id = "some-unique-id"
set_current_session(session_id)     # <- call once per agent run
start_session(session_id)

handler = BlackBoxCallbackHandler(session_id)   # <- pass this to your LLM calls for cost tracking
llm_with_tools.invoke(messages, config={"callbacks": [handler]})
```

See `agent_langchain.py` in this repo for a complete working example (uses
Groq's free tier — no credit card needed).

## Quickstart: Claude Code

Copy `.claude/settings.json` and the `blackbox/` folder into your project.
Claude Code will pick up the hooks automatically — no code changes needed.
Requires a Claude Pro/Max/Team subscription or API credits, since that's
what Claude Code itself requires.

## Configuration

Edit `config.yaml` in your project root:

```yaml
limits:
  max_session_minutes: 30
  max_tool_calls: 200
  max_spend_usd: 0.50
  spend_warning_pct: 75      # non-blocking warning before the hard limit

dangerous_bash_patterns:
  - "rm -rf"
  - "sudo rm"

dangerous_regex_patterns:
  - "drop\\s+table"

protected_paths:
  - ".env"
  - ".ssh/"

alerts:
  slack_webhook_url: "https://hooks.slack.com/..."
  enabled: true
```

No restart needed — config is re-read on every check.

## Viewing what happened

Once installed, use the `blackbox` command from your project directory:

```bash
blackbox sessions              # list recent sessions with spend
blackbox replay <session_id>   # frame-by-frame replay of one session
blackbox flags                 # everything that got flagged or blocked
blackbox stats                 # totals across all sessions
blackbox verify                # confirm the audit log hasn't been tampered with
blackbox export <session_id>   # export one session's full trail as CSV
blackbox report --days 30      # markdown compliance summary for a date range
```

## Why this exists

Agents are starting to run longer, touch more systems, and spend real money
without a human watching every step. This is the trail back to the exact
second when something went wrong — and a way to stop it before it does more
damage.

## Status

Early / pre-alpha. Built and tested against Groq (free tier) + LangChain, and
against Claude Code hooks. Not yet published to PyPI — install from source.
Feedback and bug reports very welcome.

## License

MIT
