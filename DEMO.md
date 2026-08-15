# agent-blackbox — Try it in 10 minutes

This walks you through installing agent-blackbox and watching it catch a
dangerous action in real time, before it executes.

Pick whichever path matches how you actually work. Both take about the same
amount of time. You don't need to do both.

- **Path A: Claude Code** — you already use Claude Code day to day
- **Path B: LangChain** — you build agents with LangChain (or want a
  completely free way to try this first, no subscription needed)

## What you're about to see

An AI agent will try to run a destructive shell command. agent-blackbox will
catch it, block it *before it runs*, log the attempt, track what it cost,
and ping Slack (if you set that up) — with a small, one-time setup, not a
rewrite of how you already work.

---

# Path A: Claude Code

Requires either a Claude subscription (Pro/Max/Team) or Anthropic API
credits (console.anthropic.com, pay-as-you-go, no subscription needed).

## A1. Copy the black box into your project

From this repo, copy the following into your own project's root folder:

```
your-project/
├── .claude/
│   └── settings.json
├── blackbox/
│   ├── __init__.py
│   ├── db.py
│   ├── config.py
│   ├── core.py
│   ├── guard.py
│   ├── logger.py
│   ├── session_hooks.py
│   ├── cost_hook.py
│   └── alert.py
├── config.yaml
└── view.py
```

You do **not** need `agent.py`, `agent_langchain.py`, or the
`langchain_guard.py` / `langchain_handler.py` files — those are only for
Path B.

## A2. Install the two dependencies these hooks need

```bash
pip install PyYAML requests --break-system-packages
```

## A3. Set your Claude access

If you're already logged into Claude Code via a subscription, skip this —
it'll just work. If you're using API credits instead:

**Windows PowerShell:**
```powershell
$env:ANTHROPIC_API_KEY="sk-ant-your-key-here"
```

**Mac/Linux:**
```bash
export ANTHROPIC_API_KEY=sk-ant-your-key-here
```

This only lasts for the current terminal session — you'll need to re-set it
if you close and reopen your terminal.

## A4. Launch Claude Code from inside your project folder

```bash
cd your-project
claude
```

If it asks whether to use the detected API key, choose **Yes**.

## A5. Confirm the hooks are live

Inside the Claude Code session, type:
```
/hooks
```
You should see `PreToolUse`, `PostToolUse`, `SessionStart`, `SessionEnd`,
and `Stop` listed under Project Settings. If nothing shows up, you're not
running `claude` from inside the folder that contains `.claude/settings.json`.

## A6. Run something safe first

Ask Claude Code, in the session:
```
Create a file called hello.txt with the text 'it works'
```

In a **second terminal**, same project folder (keep the Claude Code session
running in the first one):
```bash
python3 view.py sessions
python3 view.py replay <session_id_from_above>
```

You should see the `Write` tool call logged with a timestamp and input.

## A7. Now try to break it

Ask Claude Code, in the same session:
```
Run this exact shell command: sudo rm -rf /tmp/test
```

Expected: Claude Code refuses to run it and explains it was blocked.

Check it got recorded:
```bash
python3 view.py flags
```

**This is the core of the product**: the command never ran. It was
intercepted before execution, not caught after the fact.

## A8. Check your spend

Cost is computed from Claude Code's own transcript file using real,
current Anthropic API pricing — not an estimate.

```bash
python3 view.py sessions
```

You'll see a real `spend=$...` figure next to your session. It updates
live after every turn (via the `Stop` hook), and shows `ended=None` until
you fully exit the Claude Code session (`/exit` or close the terminal).

Skip to **"Turn on Slack alerts"** and **"Something not working?"** below —
both apply to this path too.

---

# Path B: LangChain (fully free, no subscription)

## B1. Get a free Groq API key (2 min)

1. Go to **console.groq.com** and sign up (no card required)
2. Generate an API key — starts with `gsk_`

## B2. Install (2 min)

```bash
git clone <this repo>   # or unzip what you were sent
cd agent-blackbox
pip install -e ".[langchain]"
```

> If you hit a dependency conflict error mentioning `langchain-core`, pull
> the latest `requirements.txt`/`pyproject.toml` — this was fixed by
> loosening the `langchain-core` version pin.

## B3. Set your key

**Windows PowerShell:**
```powershell
$env:GROQ_API_KEY="gsk_your_key_here"
```

**Mac/Linux:**
```bash
export GROQ_API_KEY=gsk_your_key_here
```

## B4. Run something safe first

```bash
python3 agent_langchain.py "Create a file called hello.txt with the text 'it works'"
```

Then check what got recorded:
```bash
blackbox sessions
blackbox replay <session_id_from_above>
```

## B5. Now try to break it

```bash
python3 agent_langchain.py "Run this exact shell command: sudo rm -rf /tmp/test"
```

Expected:
```
[run] run_bash({'command': 'sudo rm -rf /tmp/test'})
      -> This action was blocked by agent-blackbox: Command matched dangerous pattern: 'rm -rf'
```

Check the flag:
```bash
blackbox flags
```

## B6. Check your spend

```bash
blackbox stats
```

## Try it on your own LangChain tools

The entire integration for an existing LangChain tool is one decorator:

```python
from langchain_core.tools import tool
from blackbox.langchain_guard import black_box_tool, set_current_session
from blackbox.core import start_session

@tool
@black_box_tool()          # <- add this
def your_existing_tool(x: str) -> str:
    """Your existing docstring."""
    ...

session_id = "whatever-id-you-use"
set_current_session(session_id)
start_session(session_id)
```

---

# Turn on Slack alerts (optional, ~5 min, works with either path)

So a human gets pinged the moment something gets flagged, not just logged
silently:

1. Go to **api.slack.com/apps** → Create New App → From scratch
2. Enable "Incoming Webhooks", add one to a channel, copy the URL
3. Paste it into `config.yaml`:
   ```yaml
   alerts:
     slack_webhook_url: "https://hooks.slack.com/services/..."
     enabled: true
   ```
4. Re-run the dangerous command test from Step A7 or B5 — you should get a
   Slack message within a couple seconds.

---

# Configuring your rules

Both paths read the same `config.yaml` in your project. Edit
`dangerous_bash_patterns`, `max_spend_usd`, `max_session_minutes`,
`max_tool_calls`, and `allowed_tools` to match what you actually want
flagged or blocked. No restart needed — config is re-read on every check.

---

# All commands, quick reference

```bash
# Setup
pip install -r requirements.txt --break-system-packages     # Claude Code path
pip install -e ".[langchain]" --break-system-packages        # LangChain path

# Env vars (per terminal session)
$env:ANTHROPIC_API_KEY="sk-ant-..."     # PowerShell, Claude
$env:GROQ_API_KEY="gsk_..."             # PowerShell, Groq

# Running
claude                                   # launch Claude Code
python3 agent_langchain.py "task"        # LangChain + Groq agent

# Inside a Claude Code session
/hooks                                   # confirm hooks are registered
/exit                                    # cleanly end the session

# Viewing what got recorded
python3 view.py sessions                 # or: blackbox sessions
python3 view.py replay <session_id>      # or: blackbox replay <session_id>
python3 view.py flags                    # or: blackbox flags
blackbox stats                           # totals across all sessions (installed CLI only)
```

---

# Something not working?

- **"command not found: blackbox"** — the install didn't complete, or
  you're in a different terminal/venv than the one you installed into.
  Re-run `pip install -e ".[langchain]"` in the terminal you're currently
  using, or just use `python3 view.py ...` instead.
- **`ModuleNotFoundError`** — same cause as above, or you forgot
  `--break-system-packages`. Try `python3 -m pip install ...` to be sure it
  installs into the same Python that `python3` points to.
- **`claude: command not found`** — you installed the VS Code extension but
  not the CLI. Run `irm https://claude.ai/install.ps1 | iex` (Windows) and
  reopen your terminal.
- **Claude Code payment fails on an Indian card** — this is a known issue;
  most Indian debit cards block international transactions by default.
  Try enabling international transactions via your bank, or use a credit
  card. This affects both subscription and API credit purchases equally.
- **`/hooks` shows nothing** — you're not running `claude` from inside the
  folder that contains `.claude/settings.json`.
- **Groq gives a `tool_use_failed` / malformed function call error** — you're
  on a deprecated model. Check `MODEL = ` at the top of
  `agent_langchain.py` — it should be `"openai/gpt-oss-120b"`.
- **Nothing shows up in Slack** — double check `enabled: true` is actually
  set (not just the URL pasted in), and there's no trailing space in the
  webhook URL.

Found something else broken? Tell whoever sent you this — that feedback is
exactly what this stage of testing is for.
