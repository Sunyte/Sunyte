"""Tamper-evident hash chaining for the events log.

Each event's hash is computed from its own content PLUS the previous
event's hash. Editing or deleting any past row breaks every hash after
it, which `sunyte verify` detects by recomputing the whole chain.
"""

import hashlib

GENESIS_HASH = "0" * 64  # the "previous hash" for the very first event ever logged


def compute_hash(prev_hash: str, session_id: str, timestamp: str, hook_event: str,
                  tool_name: str, tool_input: str, tool_output: str, decision: str) -> str:
    payload = "|".join([
        prev_hash or GENESIS_HASH, session_id or "", timestamp or "", hook_event or "",
        tool_name or "", tool_input or "", tool_output or "", decision or "",
    ])
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
