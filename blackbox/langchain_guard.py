"""The core integration point for LangChain agents.

Usage in a real customer's codebase:

    from blackbox.langchain_guard import black_box_tool, set_current_session
    from langchain_core.tools import tool

    @tool
    @black_box_tool()
    def my_existing_tool(x: str) -> str:
        '''Docstring LangChain uses for the tool description.'''
        ...

    set_current_session(session_id)   # once, at the start of a run

That's the entire integration - two lines added to code they already have.
No fork, no framework replacement, no separate process.
"""

import functools
from blackbox.core import check_guard, log_event

_current_session_id = {"value": "default-session"}


def set_current_session(session_id: str):
    """Call once per agent run, before any tool calls happen."""
    _current_session_id["value"] = session_id


def get_current_session() -> str:
    return _current_session_id["value"]


def black_box_tool(session_id_getter=get_current_session):
    """Decorator: wraps a tool function with a guard check (before) and
    a log entry (after). Must be applied UNDER @tool (i.e. closer to the
    function) so @tool sees a function with the correct signature/docstring."""

    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            session_id = session_id_getter()
            tool_name = func.__name__
            tool_input = kwargs if kwargs else {"args": args}

            allowed, reason = check_guard(session_id, tool_name, tool_input)
            if not allowed:
                log_event(session_id, tool_name, tool_input, f"BLOCKED: {reason}", decision="block")
                return f"This action was blocked by agent-blackbox: {reason}"

            result = func(*args, **kwargs)
            log_event(session_id, tool_name, tool_input, result, decision="allow")
            return result

        return wrapper

    return decorator
