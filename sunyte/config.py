"""Loads config.yaml. Re-read on every call — hooks are short-lived processes
so there's no in-memory state to go stale."""

import os
import yaml

PROJECT_ROOT = os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd())
CONFIG_PATH = os.path.join(PROJECT_ROOT, "config.yaml")


def load_config() -> dict:
    if not os.path.exists(CONFIG_PATH):
        # sane defaults if config.yaml is missing
        return {
            "limits": {"max_session_minutes": 30, "max_tool_calls": 200},
            "allowed_tools": [],
            "blocked_tools": [],
            "dangerous_bash_patterns": [],
            "alerts": {"slack_webhook_url": "", "enabled": False},
        }
    with open(CONFIG_PATH, "r") as f:
        return yaml.safe_load(f)
