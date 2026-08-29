"""Built-in defaults for Sunyte.

These ship with the plugin so Sunyte works the moment it is installed — no
config file required. Per-project changes go through either:

  * `/sunyte-block ...`  (or `sunyte block ...` on the CLI)  -> .sunyte/rules.json
  * an optional `config.yaml` in the project root (needs PyYAML installed)

`sunyte.config.load_config()` merges all three, in that order of precedence
(rules.json wins, then config.yaml, then these defaults).
"""

# Fields that are treated as *lists of rules*: users can add to them or switch
# individual built-ins off without hand-editing the whole list.
LIST_FIELDS = [
    "dangerous_bash_patterns",
    "dangerous_regex_patterns",
    "protected_paths",
    "blocked_tools",
    "allowed_tools",
]

DEFAULTS = {
    # Where "upgrade / pricing" links point. Override per-project with
    # `sunyte config set upgrade_url ...` or the SUNYTE_UPGRADE_URL env var.
    "upgrade_url": "",

    "limits": {
        "max_session_minutes": 30,        # flag if a session runs longer than this
        "max_tool_calls": 200,            # flag if a session makes more calls than this
        "max_spend_usd": 5.00,            # kill switch: stop the session past this spend
        "spend_warning_pcts": [50, 75, 90],  # non-blocking warnings at each % of the limit
    },

    # Free tier keeps the last N sessions visible in `sunyte sessions`; older
    # sessions stay in the database and remain replayable by id, they are just
    # not listed. Team/Compliance show full history.
    "retention": {
        "free_sessions_listed": 10,
    },

    # Groq pricing for openai/gpt-oss-120b (used by the optional demo agents).
    "pricing": {
        "input_per_million_usd": 0.15,
        "output_per_million_usd": 0.60,
    },

    # Claude API pricing per million tokens. Matched by substring against the
    # model name found in the Claude Code transcript.
    "claude_pricing": {
        "sonnet-5":  {"input": 2.00, "output": 10.00, "cache_write": 2.50, "cache_read": 0.20},
        "opus-4-8":  {"input": 5.00, "output": 25.00, "cache_write": 6.25, "cache_read": 0.50},
        "haiku-4-5": {"input": 1.00, "output": 5.00,  "cache_write": 1.25, "cache_read": 0.10},
        "default":   {"input": 3.00, "output": 15.00, "cache_write": 3.75, "cache_read": 0.30},
    },

    # Tools NOT in this list are flagged as "off-path" (warn only, never blocked).
    # Empty = every tool is considered on-path.
    "allowed_tools": [],

    # Tools that are always blocked outright.
    "blocked_tools": [],

    # Substring match against the full bash command, case-insensitive.
    "dangerous_bash_patterns": [
        # destructive filesystem
        "rm -rf",
        "sudo rm",
        ":(){ :|:& };:",          # fork bomb
        "mkfs",
        "> /dev/sda",
        "> /dev/disk",
        "dd if=",
        "chmod -R 777",
        "chmod 777 /",
        # supply-chain / remote code execution
        "curl | bash",
        "curl | sh",
        "wget | bash",
        "wget | sh",
        "curl -s | bash",
        # git disasters
        "git push --force",
        "git push -f",
        "git reset --hard",
        "git clean -fdx",
        # package publishing (usually not something an agent should do unattended)
        "npm publish",
        "pypi upload",
        "twine upload",
        # cloud destructive operations
        "aws s3 rm --recursive",
        "aws s3api delete-bucket",
        "gcloud sql instances delete",
        "gcloud compute instances delete",
        "az vm delete",
        "kubectl delete namespace",
        "terraform destroy",
        # secrets / credentials
        "cat /etc/shadow",
        ".ssh/id_rsa",
    ],

    # Regex for cases a plain substring can't catch cleanly. Matched
    # case-insensitively against the full command / query text.
    "dangerous_regex_patterns": [
        r"drop\s+(table|database|schema)\b",
        r"delete\s+from\s+[\w.\"'`]+(?![\w.])(?!(?:.*\bwhere\b))",   # DELETE FROM x, no WHERE
        r"truncate\s+table",
        r"update\s+[\w.\"'`]+\s+set\b(?!(?:.*\bwhere\b))",           # UPDATE x SET ..., no WHERE
        r"rm\s+-[a-z]*r[a-z]*\s+/(?:\s|$|\*)",                       # rm -r / (any flag order)
        r"\bgit\s+push\s+.*--force(?!-with-lease)",                  # force push w/o lease
    ],

    # Paths that must never be written to, deleted, or executed against,
    # regardless of tool. Substring match against any file path or bash command.
    "protected_paths": [
        ".git/",
        ".env",
        ".ssh/",
        "id_rsa",
        "node_modules/.bin",
        "/etc/",
        "/System/",
        "C:\\Windows\\System32",
    ],

    "alerts": {
        "slack_webhook_url": "",       # Slack incoming-webhook URL (Team tier)
        "enabled": False,
        "escalation_emails": [],       # Compliance tier: who to page on a hard block
        "escalation_webhook_url": "",  # Compliance tier: where to POST escalations
    },
}
