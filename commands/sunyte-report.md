---
description: Generate a Markdown compliance / audit report (Team tier)
argument-hint: "[--days N] [--framework soc2|iso27001|nist80053]"
allowed-tools: Bash
---

Run:

```
python3 "${CLAUDE_PLUGIN_ROOT}/sunyte/cli.py" report $ARGUMENTS
```

This writes a `sunyte_report_<date>.md` file summarizing sessions, spend, blocked
actions, and log integrity for the period. `--framework` adds a control mapping
and is a Compliance-tier feature. If the command prints an upgrade notice, relay
it verbatim — do not try to work around the tier gate.
