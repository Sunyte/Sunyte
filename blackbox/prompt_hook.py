#!/usr/bin/env python3
"""UserPromptSubmit hook. Fires the moment a user submits a prompt, before
Claude processes it. We log the prompt text itself so session replay can
show WHY the agent did what it did, not just what it did. Never blocks."""

import sys
import os
import json

sys.path.insert(0, os.environ.get("CLAUDE_PROJECT_DIR", os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from blackbox.core import log_user_prompt


def main():
    raw = sys.stdin.read()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        sys.exit(0)

    session_id = data.get("session_id", "unknown")
    prompt = data.get("prompt", "")
    if prompt:
        log_user_prompt(session_id, prompt)
    sys.exit(0)  # never blocks


if __name__ == "__main__":
    main()
