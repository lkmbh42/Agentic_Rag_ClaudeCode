"""Single LLM client package — every LLM HTTP call in the app goes through
`app.llm.client` (Phase 1 requirement). Import from here or from the module."""

from app.llm.client import LLMClient, OpenAILLM, get_llm, llm_available

__all__ = ["LLMClient", "OpenAILLM", "get_llm", "llm_available"]
