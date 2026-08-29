---
description: Verify the tamper-evident Sunyte audit log has not been altered
allowed-tools: Bash
---

Run:

```
python3 "${CLAUDE_PLUGIN_ROOT}/sunyte/cli.py" verify
```

`OK` means every logged event still hashes to the chain. `TAMPERING DETECTED`
means a row in `sunyte.db` was edited or deleted after the fact — report exactly
which event the tool names and treat it as a security event, not a bug.
