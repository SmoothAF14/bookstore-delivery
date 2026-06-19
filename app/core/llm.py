"""
core/llm.py — LLM client provider for the delivery bot.

An OpenAI-compatible client pointed at OpenRouter (llm_base_url), used by the
dispatch service to let the LLM review/adjust the rule-based classification.
Shares the same LLM_API_KEY as the assistant and tracking bots.
"""
from functools import lru_cache

from app.core.config import settings


@lru_cache
def get_llm_client():
    """Return a configured OpenAI-compatible client (OpenRouter).

    Lazily imported so the service can boot (e.g. for /health) even when the
    SDK or API key is not configured.
    """
    if not settings.llm_api_key:
        raise RuntimeError(
            "LLM_API_KEY is not set — configure your OpenRouter API key before "
            "using the delivery LLM review layer."
        )

    from openai import OpenAI

    return OpenAI(api_key=settings.llm_api_key, base_url=settings.llm_base_url)
