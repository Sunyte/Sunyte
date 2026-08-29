---
description: View or change any Sunyte setting your tier allows (spend limit, timeouts, alerts…)
argument-hint: "list | set <key> <value> | reset [key]"
allowed-tools: Bash
---

The user wants to see or change Sunyte's settings for this project.

Run exactly one command:

```
python3 "${CLAUDE_PLUGIN_ROOT}/sunyte/cli.py" config $ARGUMENTS
```

If `$ARGUMENTS` is empty, run `... config list` instead.

Keys (free tier): `max-spend` (USD kill switch), `max-minutes`, `max-calls`,
`warn-pcts` (e.g. `50,75,90`), `sessions-listed`, `upgrade_url`.
Team tier adds `alerts` (true/false) and `slack_webhook_url`.
Compliance tier adds `escalation` (emails) and `escalation_webhook_url`.

Settings are written to `.sunyte/rules.json` and take effect on the next tool
call. If the command prints a tier notice, relay it — don't try to bypass it.
To edit the dangerous-command blocklist instead, use `/sunyte-block`.

After running, tell the user in one or two sentences what changed or what the
current values are.
