#!/usr/bin/env python3
"""A real LangChain agent, instrumented by Sunyte.
Compare this to agent.py - notice the tools are normal LangChain @tool
functions with ONE extra decorator (@sunyte_tool()) added. That's
the entire integration.

Usage:
  export GROQ_API_KEY=gsk_xxxxx
  python3 agent_langchain.py "your task here"
"""

import os
import sys
import uuid
import subprocess

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from langchain_core.tools import tool
from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from langchain_groq import ChatGroq

from sunyte.langchain_guard import sunyte_tool, set_current_session
from sunyte.langchain_handler import SunyteCallbackHandler
from sunyte.core import start_session, end_session, log_user_prompt

MODEL = "openai/gpt-oss-120b"
SANDBOX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sandbox")
os.makedirs(SANDBOX, exist_ok=True)
MAX_TURNS = 15


def _safe_path(path: str) -> str:
    full = os.path.abspath(os.path.join(SANDBOX, path))
    if not full.startswith(SANDBOX):
        raise ValueError("Path escapes sandbox")
    return full


# --- These are normal LangChain tools. @sunyte_tool() is the only addition. ---

@tool
@sunyte_tool()
def read_file(path: str) -> str:
    """Read a file from the sandbox directory."""
    try:
        with open(_safe_path(path), "r") as f:
            return f.read()[:3000]
    except Exception as e:
        return f"Error: {e}"


@tool
@sunyte_tool()
def write_file(path: str, content: str) -> str:
    """Write content to a file in the sandbox directory."""
    try:
        with open(_safe_path(path), "w") as f:
            f.write(content)
        return f"Wrote {len(content)} bytes to {path}"
    except Exception as e:
        return f"Error: {e}"


@tool
@sunyte_tool()
def run_bash(command: str) -> str:
    """Run a shell command inside the sandbox directory."""
    try:
        result = subprocess.run(
            command, shell=True, cwd=SANDBOX, capture_output=True, text=True, timeout=10
        )
        return (result.stdout + result.stderr)[:3000]
    except Exception as e:
        return f"Error: {e}"


TOOLS = [read_file, write_file, run_bash]
TOOLS_BY_NAME = {t.name: t for t in TOOLS}


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 agent_langchain.py \"your task here\"")
        sys.exit(1)
    task = sys.argv[1]

    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        print("Set GROQ_API_KEY first")
        sys.exit(1)

    session_id = str(uuid.uuid4())
    set_current_session(session_id)          # <- tools now log/guard against this session
    start_session(session_id, cwd=SANDBOX)
    log_user_prompt(session_id, task)
    handler = SunyteCallbackHandler(session_id)   # <- tracks cost per LLM call
    print(f"[session {session_id[:8]}] starting: {task}\n")

    llm = ChatGroq(model=MODEL, api_key=api_key, temperature=0.7)
    llm_with_tools = llm.bind_tools(TOOLS)

    messages = [
        SystemMessage(content="You are a coding agent. You have read_file, write_file, and run_bash "
                               "tools, all sandboxed to one working directory. Use them to complete the task."),
        HumanMessage(content=task),
    ]

    for turn in range(MAX_TURNS):
        response = llm_with_tools.invoke(messages, config={"callbacks": [handler]})
        messages.append(response)

        if handler.killed:
            print(f"[KILLED] {handler.kill_reason}")
            break

        if not response.tool_calls:
            print(f"\n[agent] {response.content}")
            break

        for tc in response.tool_calls:
            tool_obj = TOOLS_BY_NAME.get(tc["name"])
            print(f"[run] {tc['name']}({tc['args']})")
            if tool_obj is None:
                result = f"Unknown tool: {tc['name']}"
            else:
                result = tool_obj.invoke(tc["args"])   # guard + logging happen inside automatically
            print(f"      -> {str(result)[:200]}")
            messages.append(ToolMessage(content=str(result), tool_call_id=tc["id"]))
    else:
        print("\n[agent] Reached max turns without finishing.")

    end_session(session_id)
    print(f"\n[session {session_id[:8]}] done. Inspect with: python3 view.py replay {session_id[:8]}")


if __name__ == "__main__":
    main()
