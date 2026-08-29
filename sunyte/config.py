"""Resolves the effective Sunyte config for a project.

Precedence (lowest to highest):

  1. sunyte/defaults.py            -- ships with the plugin, always present
  2. <project>/config.yaml         -- optional, only read if PyYAML is installed
  3. <project>/.sunyte/rules.json  -- written by `/sunyte-block` / `sunyte block`

Re-read on every call. Hooks are short-lived processes, so there is no
in-memory state to go stale.
"""

import os
import copy
import json

from sunyte.defaults import DEFAULTS, LIST_FIELDS


def project_root() -> str:
    return os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd())


def sunyte_dir() -> str:
    return os.path.join(project_root(), ".sunyte")


def rules_path() -> str:
    return os.path.join(sunyte_dir(), "rules.json")


def config_yaml_path() -> str:
    return os.path.join(project_root(), "config.yaml")


def _load_yaml() -> dict:
    path = config_yaml_path()
    if not os.path.exists(path):
        return {}
    try:
        import yaml  # optional dependency
    except ImportError:
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception:
        return {}


def load_rules() -> dict:
    """The raw contents of .sunyte/rules.json (or {} if absent/unreadable)."""
    path = rules_path()
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _deep_merge(base: dict, over: dict):
    for key, value in (over or {}).items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value


def load_config() -> dict:
    cfg = copy.deepcopy(DEFAULTS)

    yaml_cfg = _load_yaml()
    # Non-list keys (limits, alerts, pricing, ...) are deep-merged.
    _deep_merge(cfg, {k: v for k, v in yaml_cfg.items() if k not in LIST_FIELDS})

    rules = load_rules()
    added = rules.get("add", {}) or {}
    removed = rules.get("remove", {}) or {}

    # List fields are always ADDITIVE: built-in defaults, plus anything in
    # config.yaml, plus user additions from rules.json, minus user removals.
    for field in LIST_FIELDS:
        merged = list(cfg.get(field, []) or [])
        for source in (yaml_cfg.get(field, []) or [], added.get(field, []) or []):
            for item in source:
                if item not in merged:
                    merged.append(item)
        drop = set(removed.get(field, []) or [])
        cfg[field] = [item for item in merged if item not in drop]

    for section in ("limits", "alerts", "retention"):
        if isinstance(rules.get(section), dict):
            cfg.setdefault(section, {}).update(rules[section])

    for scalar in ("upgrade_url",):
        if scalar in rules and not isinstance(rules[scalar], (dict, list)):
            cfg[scalar] = rules[scalar]

    return cfg
