"""Tier-aware settings that a user can change themselves.

`sunyte config` / `/sunyte-config` expose every non-list setting Sunyte has.
Which ones you're *allowed* to change depends on your tier:

  free        limits, retention, the upgrade/pricing URL
  team        + Slack / webhook alerting
  compliance  + escalation (who gets paged on a hard block)

Changes are written to .sunyte/rules.json and merged over the built-in defaults
on the next check. (Dangerous-command / protected-path lists are edited
separately with `sunyte block` because they're add/remove lists, not values.)
"""

import os
import json

from sunyte.config import load_config, load_rules, rules_path, sunyte_dir
from sunyte import tier as tiers


class _Setting:
    def __init__(self, key, section, kind, min_tier, help, aliases=()):
        self.key = key
        self.section = section          # "" means a top-level key
        self.kind = kind
        self.min_tier = min_tier
        self.help = help
        self.aliases = aliases


SETTINGS = [
    _Setting("max_spend_usd", "limits", "pos_float", "free",
             "Hard spend kill switch, in USD", ("max-spend", "spend")),
    _Setting("max_session_minutes", "limits", "pos_int", "free",
             "Stop a session after this many minutes", ("max-minutes", "minutes")),
    _Setting("max_tool_calls", "limits", "pos_int", "free",
             "Stop a session after this many tool calls", ("max-calls", "calls")),
    _Setting("spend_warning_pcts", "limits", "pcts", "free",
             "Warn at each of these percentages of the spend limit", ("warn-pcts",)),
    _Setting("free_sessions_listed", "retention", "pos_int", "free",
             "How many recent sessions `sunyte sessions` lists", ("sessions-listed",)),
    _Setting("upgrade_url", "", "str", "free",
             "Where upgrade / pricing links point", ("pricing-url",)),
    _Setting("enabled", "alerts", "bool", "team",
             "Push an alert to Slack/webhook when something is flagged", ("alerts",)),
    _Setting("slack_webhook_url", "alerts", "str", "team",
             "Slack incoming-webhook URL", ("slack",)),
    _Setting("escalation_emails", "alerts", "str_list", "compliance",
             "Comma-separated addresses to page on a hard block", ("escalation",)),
    _Setting("escalation_webhook_url", "alerts", "str", "compliance",
             "Webhook to POST escalations to", ()),
]

_BY_NAME = {}
for _s in SETTINGS:
    _BY_NAME[_s.key] = _s
    _BY_NAME[_s.key.replace("_", "-")] = _s
    for _a in _s.aliases:
        _BY_NAME[_a] = _s


def _find(name: str) -> _Setting:
    s = _BY_NAME.get((name or "").strip().lower())
    if not s:
        raise ValueError(f"Unknown setting '{name}'. Run `sunyte config list` to see them all.")
    return s


def _coerce(kind: str, raw):
    if kind == "pos_float":
        v = float(raw)
        if v <= 0:
            raise ValueError("must be a number greater than 0")
        return v
    if kind == "pos_int":
        v = int(str(raw).strip())
        if v <= 0:
            raise ValueError("must be a whole number greater than 0")
        return v
    if kind == "pcts":
        vals = sorted({int(x) for x in str(raw).replace(" ", "").split(",") if x})
        if not vals or any(p <= 0 or p >= 100 for p in vals):
            raise ValueError("give 1-99 percentages, e.g. 50,75,90")
        return vals
    if kind == "bool":
        low = str(raw).strip().lower()
        if low in ("1", "true", "yes", "on"):
            return True
        if low in ("0", "false", "no", "off"):
            return False
        raise ValueError("use true or false")
    if kind == "str":
        return str(raw)
    if kind == "str_list":
        return [x.strip() for x in str(raw).split(",") if x.strip()]
    raise ValueError(f"unknown kind {kind}")


def _save(rules: dict):
    os.makedirs(sunyte_dir(), exist_ok=True)
    with open(rules_path(), "w", encoding="utf-8") as f:
        json.dump(rules, f, indent=2)
        f.write("\n")


def _current_value(cfg: dict, s: _Setting):
    return cfg.get(s.section, {}).get(s.key) if s.section else cfg.get(s.key)


def set_setting(name: str, raw) -> str:
    s = _find(name)
    if not tiers.at_least(s.min_tier):
        return (f"'{s.key}' is a {s.min_tier.capitalize()}-tier setting - you're on "
                f"{tiers.get_tier().capitalize()}.\n  {tiers.upgrade_url()}")
    value = _coerce(s.kind, raw)
    rules = load_rules() or {}
    if s.section:
        rules.setdefault(s.section, {})[s.key] = value
    else:
        rules[s.key] = value
    _save(rules)
    return f"Set {s.key} = {value!r}."


def reset_setting(name: str = None) -> str:
    rules = load_rules() or {}
    if name is None:
        for section in ("limits", "alerts", "retention"):
            rules.pop(section, None)
        rules.pop("upgrade_url", None)
        _save(rules)
        return "All setting overrides cleared - back to defaults (blocklist untouched)."
    s = _find(name)
    if s.section:
        rules.get(s.section, {}).pop(s.key, None)
        if not rules.get(s.section):
            rules.pop(s.section, None)
    else:
        rules.pop(s.key, None)
    _save(rules)
    return f"Reset {s.key} to its default."


def describe() -> str:
    cfg = load_config()
    lines = [f"Settings (tier: {tiers.get_tier().upper()}) - "
             f"change with `sunyte config set <key> <value>`:\n"]
    for s in SETTINGS:
        val = _current_value(cfg, s)
        lock = "" if tiers.at_least(s.min_tier) else f"   [{s.min_tier.upper()} tier]"
        lines.append(f"  {s.key:<22} {val!r}{lock}")
        lines.append(f"  {'':<22} {s.help}")
    return "\n".join(lines)
