---
description: Show or edit the commands Sunyte blocks before they run
argument-hint: "list | add \"<pattern>\" | add --regex \"<re>\" | add --path \"<p>\" | remove \"<pattern>\" | reset"
allowed-tools: Bash
---

The user wants to inspect or change Sunyte's dangerous-command blocklist for this project.

Run exactly one command:

```
python3 "${CLAUDE_PLUGIN_ROOT}/sunyte/cli.py" block $ARGUMENTS
```

If `$ARGUMENTS` is empty, run `python3 "${CLAUDE_PLUGIN_ROOT}/sunyte/cli.py" block list` instead.

Notes for interpreting the request:
- A bare phrase after `add` / `remove` is a substring match against shell commands
  (e.g. `add "npm publish"`).
- `--regex` adds a regular expression, `--path` adds a protected file path,
  `--tool` hard-blocks a tool by name.
- Changes are written to `.sunyte/rules.json` in the project and take effect on the
  very next tool call — no restart.

After running, tell the user in one or two sentences what the blocklist now contains
or what changed. Do not run any other commands or edit any files yourself.
