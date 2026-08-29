# Sunyte — try it in 10 minutes

You'll watch an AI agent try to run a destructive command, and watch Sunyte
catch it *before it runs*, log the attempt, and track what the session cost.

Pick the path that matches how you work. You don't need both.

- **Path A: Claude Code plugin** — you use Claude Code day to day
- **Path B: LangChain + Groq** — fully free, no subscription needed

---

# Path A: Claude Code plugin

Requires `python3` on your PATH and a Claude subscription or API credits.

## A1. Install

Inside Claude Code:

```
/plugin marketplace add Sunyte/Sunyte
/plugin install sunyte@sunyte
```

(Or, without the marketplace: copy `sunyte/` and `.claude/settings.json` from
this repo into your project.)

## A2. Confirm it's live

```
/sunyte-status
```

You should see `tier: FREE`, a spend kill switch, and a count of blocked
commands and protected paths. `/hooks` should also list the five Sunyte hooks.

## A3. Run something safe

Ask Claude Code:

```
Create a file called hello.txt with the text 'it works'
```

Then:

```
/sunyte-sessions
/sunyte-replay <id from the list>
```

You'll see the `Write` call logged with a timestamp.

## A4. Now try to break it

```
Run this exact shell command: sudo rm -rf /tmp/test
```
```
Read the .env file in this project
```
```
Run this exact SQL: DELETE FROM users
```

All three are blocked — one by a dangerous-command pattern, one by the
protected-paths rule, one by the regex that catches a `DELETE` with no `WHERE`.

```
/sunyte-flags
```

**This is the core of the product**: the command never ran. It was intercepted
before execution, not caught afterward.

## A5. Make the blocklist yours

```
/sunyte-block add "flyctl deploy"
/sunyte-block
```

Now ask Claude Code to run `flyctl deploy --now` — blocked. Changed your mind?

```
/sunyte-block remove "flyctl deploy"
```

Effective on the next tool call, no restart.

## A6. Check your spend

```
/sunyte-sessions
```

The `spend=$…` figure is computed from Claude Code's own transcript using
current Anthropic pricing. It updates after every turn.

## A7. Prove the log is trustworthy

```
/sunyte-verify
```

`OK` means every logged event still hashes to the chain. Edit a row in
`sunyte.db` by hand and run it again — it will name the exact event you changed.

---

# Path B: LangChain (fully free)

## B1. Free Groq key

Sign up at **console.groq.com** (no card), make a key starting `gsk_`.

## B2. Install

```bash
git clone https://github.com/Sunyte/Sunyte
cd Sunyte
pip install -e ".[langchain]"
```

## B3. Set your key

```bash
export GROQ_API_KEY=gsk_your_key_here          # PowerShell: $env:GROQ_API_KEY="gsk_..."
```

## B4. Safe, then dangerous

```bash
python3 agent_langchain.py "Create a file called hello.txt with the text 'it works'"
python3 agent_langchain.py "Run this exact shell command: sudo rm -rf /tmp/test"
```

Expected on the second one:

```
[run] run_bash({'command': 'sudo rm -rf /tmp/test'})
      -> This action was blocked by Sunyte: Command matched dangerous pattern: 'rm -rf'
```

```bash
sunyte flags
sunyte replay <session_id>
sunyte stats
```

---

# Slack alerts (Team tier, optional)

1. api.slack.com/apps → Create New App → From scratch
2. Enable Incoming Webhooks, add one to a channel, copy the URL
3. Put it in `config.yaml`:
   ```yaml
   alerts:
     slack_webhook_url: "https://hooks.slack.com/services/..."
     enabled: true
   ```
4. `sunyte tier activate <your-team-token>`
5. Re-run a dangerous command — you get a Slack ping within seconds.

---

# Audit & compliance commands

```bash
sunyte verify                    # tamper-evidence check (Free)
sunyte search "prod database"    # cross-session search (Team)
sunyte export <session_id>       # full audit trail as CSV (Team)
sunyte report --days 30          # Markdown compliance summary (Team)
sunyte report --framework soc2   # + control mapping (Compliance)
sunyte sign --days 30            # signed, verifiable audit manifest (Compliance)
```

---

# Troubleshooting

- **`/sunyte-*` commands not found** — the plugin didn't install, or you're not
  in a project. Re-run `/plugin install sunyte@sunyte`.
- **`python3: command not found` (Windows)** — install Python and make sure
  `python3` (not just `python`) resolves; Claude Code needs it for hooks too.
- **`/hooks` shows nothing** (manual install) — you're not running `claude` from
  the folder containing `.claude/settings.json`.
- **`command not found: sunyte`** (Path B) — you're in a different venv than the
  one you `pip install`ed into. Use `python3 -m sunyte.cli ...` or
  `python3 view.py ...`.
- **`sunyte verify` reports tampering** — a row in `sunyte.db` was edited or
  deleted after being logged. That's the feature working; investigate what
  touched the database file directly.
- **Claude Code payment fails on an Indian card** — most Indian debit cards
  block international transactions by default; enable that with your bank or use
  a credit card. Affects subscriptions and API credits equally.
