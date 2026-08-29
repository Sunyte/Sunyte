---
description: Show everything Sunyte has flagged or blocked
argument-hint: "[session_id]"
allowed-tools: Bash
---

Run:

```
python3 "${CLAUDE_PLUGIN_ROOT}/sunyte/cli.py" flags $ARGUMENTS
```

Summarize what was blocked vs. warned. If something was blocked that the user
actually wants to allow, point them at `/sunyte-block remove "<pattern>"`.
