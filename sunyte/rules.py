"""Read/write helpers for the user-owned rule overrides in .sunyte/rules.json.

This is what powers `/sunyte-block` and `sunyte block ...` — it lets a user
add their own dangerous patterns, or switch a built-in off, without ever
hand-editing a list. The built-in defaults are never mutated; rules.json only
records the *delta* (things added, things removed).
"""

import os
import json

from sunyte.config import rules_path, sunyte_dir, load_rules, load_config
from sunyte.defaults import DEFAULTS, LIST_FIELDS

# Friendly names accepted on the CLI / slash command.
FIELD_ALIASES = {
    "bash": "dangerous_bash_patterns",
    "command": "dangerous_bash_patterns",
    "cmd": "dangerous_bash_patterns",
    "regex": "dangerous_regex_patterns",
    "path": "protected_paths",
    "tool": "blocked_tools",
    "allow-tool": "allowed_tools",
}

LABELS = {
    "dangerous_bash_patterns": "blocked commands (substring)",
    "dangerous_regex_patterns": "blocked commands (regex)",
    "protected_paths": "protected paths",
    "blocked_tools": "hard-blocked tools",
    "allowed_tools": "allowed (on-path) tools",
}


def resolve_field(name: str) -> str:
    name = (name or "").strip().lower()
    if name in LIST_FIELDS:
        return name
    if name in FIELD_ALIASES:
        return FIELD_ALIASES[name]
    raise ValueError(
        f"Unknown rule type '{name}'. Use one of: "
        + ", ".join(sorted(set(list(FIELD_ALIASES) + LIST_FIELDS)))
    )


def _save(rules: dict):
    os.makedirs(sunyte_dir(), exist_ok=True)
    with open(rules_path(), "w", encoding="utf-8") as f:
        json.dump(rules, f, indent=2)
        f.write("\n")


def _blank() -> dict:
    return {
        "add": {f: [] for f in LIST_FIELDS},
        "remove": {f: [] for f in LIST_FIELDS},
    }


def _normalize(rules: dict) -> dict:
    base = _blank()
    for bucket in ("add", "remove"):
        for field, items in (rules.get(bucket, {}) or {}).items():
            if field in base[bucket]:
                base[bucket][field] = list(items or [])
    # Carry through everything else untouched (limits, alerts, retention,
    # upgrade_url, and anything `sunyte config` writes in future).
    for key, value in (rules or {}).items():
        if key not in ("add", "remove"):
            base[key] = value
    return base


def add_rule(field: str, pattern: str) -> str:
    field = resolve_field(field)
    pattern = pattern.strip()
    if not pattern:
        raise ValueError("Pattern is empty.")
    rules = _normalize(load_rules())
    # Cancel a prior removal of this exact built-in, if any.
    rules["remove"][field] = [p for p in rules["remove"][field] if p != pattern]
    if pattern in DEFAULTS.get(field, []):
        _save(rules)
        return f"'{pattern}' is already a built-in {LABELS[field]} rule (nothing to add)."
    if pattern in rules["add"][field]:
        return f"'{pattern}' is already in your {LABELS[field]} list."
    rules["add"][field].append(pattern)
    _save(rules)
    return f"Added '{pattern}' to {LABELS[field]}."


def remove_rule(field: str, pattern: str) -> str:
    field = resolve_field(field)
    pattern = pattern.strip()
    rules = _normalize(load_rules())
    changed = False
    if pattern in rules["add"][field]:
        rules["add"][field] = [p for p in rules["add"][field] if p != pattern]
        changed = True
    if pattern in DEFAULTS.get(field, []) and pattern not in rules["remove"][field]:
        rules["remove"][field].append(pattern)
        changed = True
    if not changed:
        return f"'{pattern}' is not an active {LABELS[field]} rule."
    _save(rules)
    return f"Removed '{pattern}' from {LABELS[field]}."


def remove_any(pattern: str) -> str:
    """Remove a rule by its text without needing to know which list it's in."""
    pattern = pattern.strip()
    cfg = load_config()
    hits = [f for f in LIST_FIELDS
            if pattern in cfg.get(f, []) or pattern in DEFAULTS.get(f, [])]
    if not hits:
        return f"'{pattern}' is not an active rule in any list."
    return "\n".join(remove_rule(f, pattern) for f in hits)


def reset_field(field: str) -> str:
    field = resolve_field(field)
    rules = _normalize(load_rules())
    rules["add"][field] = []
    rules["remove"][field] = []
    _save(rules)
    return f"Reset {LABELS[field]} back to the built-in defaults."


def reset_all() -> str:
    if os.path.exists(rules_path()):
        os.remove(rules_path())
    return "All rule overrides cleared - back to built-in defaults."


def describe() -> str:
    """A human-readable view of every active rule and where it came from."""
    cfg = load_config()
    rules = _normalize(load_rules())
    out = []
    for field in LIST_FIELDS:
        active = cfg.get(field, [])
        if not active and not rules["remove"][field]:
            continue
        out.append(f"\n{LABELS[field]}:")
        user_added = set(rules["add"][field])
        for item in active:
            tag = "  (yours)" if item in user_added else ""
            out.append(f"  + {item}{tag}")
        for item in rules["remove"][field]:
            out.append(f"  - {item}  (built-in, disabled by you)")
    return "\n".join(out) if out else "No rules configured."
