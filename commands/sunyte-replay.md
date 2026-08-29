---
description: Frame-by-frame replay of one Sunyte session
argument-hint: "<session_id>  (a short prefix is fine)"
allowed-tools: Bash
---

Run:

```
python3 "${CLAUDE_PLUGIN_ROOT}/sunyte/cli.py" replay $ARGUMENTS
```

If `$ARGUMENTS` is empty, first run `... sessions`, show the list, and ask which one.

Present the timeline to the user as-is. Call out any line marked `BLOCKED`.
