---
description: List recent Sunyte sessions with their spend and status
allowed-tools: Bash
---

Run:

```
python3 "${CLAUDE_PLUGIN_ROOT}/sunyte/cli.py" sessions
```

Show the user the list. If they name a session afterwards, they can replay it with
`/sunyte-replay <id>`.
