---
description: Search every recorded session's prompts, commands, and outputs (Team tier)
argument-hint: "<text to find>"
allowed-tools: Bash
---

Run:

```
python3 "${CLAUDE_PLUGIN_ROOT}/sunyte/cli.py" search $ARGUMENTS
```

Show the matching events grouped by session. If the command prints an upgrade
notice, relay it verbatim.
