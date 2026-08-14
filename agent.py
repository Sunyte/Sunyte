#!/usr/bin/env python3
"""A tiny agent loop powered by Groq's free API.
Every tool call goes through: check_guard() -> execute (if allowed) -> log_event()
This mirrors exactly what the Claude Code hooks do, just called directly.

Usage:
  export GROQ_API_KEY=gsk_xxxxx
  python3 agent.py "your task here"
"""

import os
import sys
import json
import uuid
import subprocess
from groq import Groq

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from blackbox.core import start_session, end_session, log_event, check_guard, log_model_usage, check_spend_limit, get_session_cost

MODEL = "openai/gpt-oss-120b"
SANDBOX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sandbox")
os.makedirs(SANDBOX, exist_ok=True)
MAX_TURNS = 15

# --- Tool implementations (sandboxed to one folder for safety) ---

def _safe_path(path: str) -> str:
    full = os.path.abspath(os.path.join(SANDBOX, path))
    if not full.startswith(SANDBOX):
        raise ValueError("Path escapes sandbox")
    return full

def read_file(path: str) -> str:
    try:
        with open(_safe_path(path), "r") as f:
            return f.read()[:3000]
    except Exception as e:
        return f"Error: {e}"

def write_file(path: str, content: str) -> str:
    try:
        with open(_safe_path(path), "w") as f:
            f.write(content)
        return f"Wrote {len(content)} bytes to {path}"
    except Exception as e:
        return f"Error: {e}"

def run_bash(command: str) -> str:
    try:
        result = subprocess.run(
            command, shell=True, cwd=SANDBOX, capture_output=True, text=True, timeout=10
        )
        return (result.stdout + result.stderr)[:3000]
    except Exception as e:
        return f"Error: {e}"

TOOL_FUNCS = {"read_file": read_file, "write_file": write_file, "run_bash": run_bash}

TOOL_SCHEMAS = [
    {"type": "function", "function": {
        "name": "read_file", "description": "Read a file from the sandbox directory.",
        "parameters": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}}},
    {"type": "function", "function": {
        "name": "write_file", "description": "Write content to a file in the sandbox directory.",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string"}, "content": {"type": "string"}}, "required": ["path", "content"]}}},
    {"type": "function", "function": {
        "name": "run_bash", "description": "Run a shell command inside the sandbox directory.",
        "parameters": {"type": "object", "properties": {"command": {"type": "string"}}, "required": ["command"]}}},
]


def _call_with_retry(client, messages, max_retries=3):
    """Groq occasionally emits a malformed tool call. Retry with lower
    temperature, per Groq's own recommended fix."""
    import groq
    temperature = 0.7
    for attempt in range(max_retries):
        try:
            return client.chat.completions.create(
                model=MODEL, messages=messages, tools=TOOL_SCHEMAS,
                tool_choice="auto", temperature=temperature,
            )
        except groq.BadRequestError as e:
            if attempt == max_retries - 1:
                raise
            print(f"[retry {attempt + 1}] malformed tool call, lowering temperature and retrying...")
            temperature = max(0.1, temperature - 0.3)


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 agent.py \"your task here\"")
        sys.exit(1)
    task = sys.argv[1]

    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        print("Set GROQ_API_KEY first: export GROQ_API_KEY=gsk_xxxxx")
        sys.exit(1)

    client = Groq(api_key=api_key)
    session_id = str(uuid.uuid4())
    start_session(session_id, cwd=SANDBOX)
    print(f"[session {session_id[:8]}] starting: {task}\n")

    messages = [
        {"role": "system", "content": "You are a coding agent. You have read_file, write_file, and run_bash "
                                       "tools, all sandboxed to one working directory. Use them to complete the task."},
        {"role": "user", "content": task},
    ]

    for turn in range(MAX_TURNS):
        response = _call_with_retry(client, messages)
        msg = response.choices[0].message

        usage = response.usage
        call_cost = log_model_usage(session_id, usage.prompt_tokens, usage.completion_tokens)
        running_total = get_session_cost(session_id)
        print(f"[usage] +${call_cost:.5f} this call, ${running_total:.5f} total this session")

        spend_ok, spend_reason = check_spend_limit(session_id)
        if not spend_ok:
            print(f"[KILLED] {spend_reason}")
            break

        if not msg.tool_calls:
            print(f"\n[agent] {msg.content}")
            break

        messages.append(msg)

        for tc in msg.tool_calls:
            tool_name = tc.function.name
            try:
                tool_input = json.loads(tc.function.arguments)
            except json.JSONDecodeError:
                tool_input = {}

            allowed, reason = check_guard(session_id, tool_name, tool_input)

            if not allowed:
                print(f"[BLOCKED] {tool_name}({tool_input}) -> {reason}")
                log_event(session_id, tool_name, tool_input, f"BLOCKED: {reason}", decision="block")
                result = f"This action was blocked by the black-box safety layer: {reason}"
            else:
                print(f"[run] {tool_name}({tool_input})")
                func = TOOL_FUNCS.get(tool_name)
                result = func(**tool_input) if func else f"Unknown tool: {tool_name}"
                log_event(session_id, tool_name, tool_input, result, decision="allow")
                print(f"      -> {str(result)[:200]}")

            messages.append({
                "role": "tool", "tool_call_id": tc.id, "name": tool_name, "content": str(result),
            })
    else:
        print("\n[agent] Reached max turns without finishing.")

    end_session(session_id)
    print(f"\n[session {session_id[:8]}] done. Inspect with: python3 view.py replay {session_id[:8]}")


if __name__ == "__main__":
    main()
