#!/usr/bin/env python3
"""Stop hook. Fires after each Claude Code turn. Reads the transcript file
Claude Code already writes (path given to us via stdin) and recomputes the
FULL session cost from scratch each time - this is deliberately idempotent
(overwrite, not add) so firing multiple times per session never double-counts."""

import sys
import os
import json
import datetime

sys.path.insert(0, os.environ.get("CLAUDE_PROJECT_DIR", os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from blackbox.db import get_conn
from blackbox.config import load_config
from blackbox.alert import send_alert


def price_for_model(model_name: str, pricing_table: dict) -> dict:
    if not model_name:
        return pricing_table.get("default", {"input": 3.0, "output": 15.0, "cache_write": 3.75, "cache_read": 0.30})
    for key, rates in pricing_table.items():
        if key != "default" and key in model_name:
            return rates
    return pricing_table.get("default", {"input": 3.0, "output": 15.0, "cache_write": 3.75, "cache_read": 0.30})


def compute_cost_from_transcript(transcript_path: str, pricing_table: dict):
    """Returns (total_cost_usd, total_input_tokens, total_output_tokens)."""
    total_cost = 0.0
    
    total_in = 0
    total_out = 0

    if not transcript_path or not os.path.exists(transcript_path):
        return total_cost, total_in, total_out

    with open(transcript_path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue

            # assistant turns carry a "message" object with "usage" and "model"
            message = entry.get("message", {})
            usage = message.get("usage")
            if not usage:
                continue

            model = message.get("model", "")
            rates = price_for_model(model, pricing_table)

            in_tok = usage.get("input_tokens", 0) or 0
            out_tok = usage.get("output_tokens", 0) or 0
            cache_write = usage.get("cache_creation_input_tokens", 0) or 0
            cache_read = usage.get("cache_read_input_tokens", 0) or 0

            total_in += in_tok
            total_out += out_tok

            total_cost += (in_tok / 1_000_000) * rates["input"]
            total_cost += (out_tok / 1_000_000) * rates["output"]
            total_cost += (cache_write / 1_000_000) * rates.get("cache_write", rates["input"] * 1.25)
            total_cost += (cache_read / 1_000_000) * rates.get("cache_read", rates["input"] * 0.1)

    return total_cost, total_in, total_out


def main():
    raw = sys.stdin.read()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        sys.exit(0)

    session_id = data.get("session_id", "unknown")
    transcript_path = data.get("transcript_path", "")
    cfg = load_config()
    pricing_table = cfg.get("claude_pricing", {})

    cost, in_tok, out_tok = compute_cost_from_transcript(transcript_path, pricing_table)

    conn = get_conn()
    # make sure a session row exists even if SessionStart was somehow missed
    conn.execute(
        "INSERT OR IGNORE INTO sessions (session_id, started_at, status) VALUES (?, ?, 'running')",
        (session_id, datetime.datetime.now(datetime.timezone.utc).isoformat()),
    )
    conn.execute(
        "UPDATE sessions SET total_cost_usd = ?, total_input_tokens = ?, total_output_tokens = ? WHERE session_id = ?",
        (cost, in_tok, out_tok, session_id),
    )
    conn.commit()

    max_spend = cfg.get("limits", {}).get("max_spend_usd", 999999)
    if cost >= max_spend:
        conn.execute(
            "INSERT INTO flags (session_id, rule_name, severity, message, timestamp) VALUES (?, ?, ?, ?, ?)",
            (session_id, "max_spend", "block", f"Session has spent ${cost:.4f}, exceeding limit of ${max_spend}.",
             datetime.datetime.now(datetime.timezone.utc).isoformat()),
        )
        conn.commit()
        send_alert(f"Session {session_id[:8]} has spent ${cost:.4f}, over the ${max_spend} limit.")

    conn.close()
    sys.exit(0)


if __name__ == "__main__":
    main()
