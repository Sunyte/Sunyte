---
description: Show the active Sunyte tier or activate a Team / Compliance license
argument-hint: "[activate <token>]"
allowed-tools: Bash
---

Run:

```
python3 "${CLAUDE_PLUGIN_ROOT}/sunyte/cli.py" tier $ARGUMENTS
```

Free tier covers pre-execution blocking, the kill switch, per-session logging and
replay, and self-editing the blocklist. Team adds Slack alerts, CSV/Markdown
exports, and cross-session search. Compliance adds cryptographically signed audit
manifests, framework mapping (SOC 2 / ISO 27001 / NIST 800-53), and escalation
policies. Relay the tool output and this summary; do not invent pricing numbers.
