# Changelog

## 0.2.0 — Claude Code plugin

### Added
- **Claude Code plugin packaging.** `.claude-plugin/plugin.json` +
  `.claude-plugin/marketplace.json`, plugin hooks in `hooks/hooks.json`,
  slash commands in `commands/`, and a `sunyte-auditor` subagent.
  Install with `/plugin marketplace add Sunyte/Sunyte` then
  `/plugin install sunyte@sunyte`.
- **Zero runtime dependencies.** The core engine now runs on the Python
  standard library alone — `requests` replaced with `urllib`, `PyYAML` made
  optional. `config.yaml` is honored only if PyYAML is installed.
- **User-editable blocklist.** `/sunyte-block` (and `sunyte block ...`) let you
  add or disable dangerous-command patterns, regexes, protected paths, and
  hard-blocked tools without hand-editing config. Stored as a delta in
  `.sunyte/rules.json`; built-in defaults are never mutated.
- **Self-service settings.** `/sunyte-config` (and `sunyte config ...`) let you
  change the spend kill switch, session/tool-call limits, warning thresholds,
  retention, alert webhooks, and escalation targets. Each setting declares a
  minimum tier, so the command shows exactly what you can change.
- **Configurable upgrade URL** (`SUNYTE_UPGRADE_URL` env / `upgrade_url`
  setting) — pricing links no longer have to point at a fixed GitHub repo.
- **Built-in defaults** moved into `sunyte/defaults.py` so Sunyte works with no
  config file at all.
- **Tier scaffolding** (`sunyte/tier.py`): Free / Team / Compliance, activated
  via `SUNYTE_LICENSE` or `.sunyte/license.key`. New commands: `sunyte tier`,
  `sunyte status`, `sunyte search` (Team), `sunyte sign` (Compliance),
  `sunyte report --framework` (Compliance).
- `sunyte status` — tier, guardrails, spend limit, and log integrity at a glance.

### Changed
- Slack/webhook alerting is now a Team-tier feature; every flag is still
  recorded locally on Free.
- `sunyte sessions` on Free lists the 10 most recent sessions (older ones stay
  in the DB and remain replayable by id); Team/Compliance show full history.
- Hook scripts locate the bundled `sunyte` package next to themselves, so they
  work identically whether installed as a plugin or copied into a project.
- More precise `DELETE`/`UPDATE`-without-`WHERE` regexes; added `dd if=`,
  `npm publish`, `twine upload`, force-push-without-lease patterns.
- Default `max_spend_usd` raised from 0.01 to 5.00.

## 0.1.0
- Initial release: PreToolUse blocking, cost tracking, tamper-evident log,
  session replay, LangChain integration.
