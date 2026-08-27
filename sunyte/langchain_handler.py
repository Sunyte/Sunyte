"""LangChain callback handler for cost tracking.

Usage:
    handler = SunyteCallbackHandler(session_id)
    llm.invoke(messages, config={"callbacks": [handler]})

This is LangChain's own recommended extension mechanism (BaseCallbackHandler),
not something bolted on from outside - so it should work with any
LangChain-compatible chat model, not just Groq.
"""

from langchain_core.callbacks import BaseCallbackHandler
from sunyte.core import log_model_usage, check_spend_limit


class SunyteCallbackHandler(BaseCallbackHandler):
    def __init__(self, session_id: str):
        self.session_id = session_id
        self.killed = False
        self.kill_reason = ""

    def on_llm_end(self, response, **kwargs):
        try:
            usage = {}
            model = ""
            if response.llm_output:
                usage = response.llm_output.get("token_usage", {}) or response.llm_output.get("usage", {})
                model = response.llm_output.get("model_name", "") or response.llm_output.get("model", "")
            prompt_tokens = usage.get("prompt_tokens", 0)
            completion_tokens = usage.get("completion_tokens", 0)
            if prompt_tokens or completion_tokens:
                log_model_usage(self.session_id, prompt_tokens, completion_tokens, model=model)

            ok, reason = check_spend_limit(self.session_id)
            if not ok:
                self.killed = True
                self.kill_reason = reason
        except Exception:
            pass  # never let observability break the agent's actual work
