"""
LLM backend abstraction.

Providers
---------
  none    — disabled (raises LLMError on any call)
  ollama  — local Ollama server (default: http://localhost:11434)
  openai  — OpenAI-compatible API (any base URL + optional API key)

Configuration via environment variables:
  AGENT_LLM_PROVIDER  none | ollama | openai
  AGENT_LLM_MODEL     model name, e.g. llama3.2 or gpt-4o-mini
  AGENT_LLM_BASE_URL  base URL (Ollama or OpenAI-compatible endpoint)
  AGENT_LLM_API_KEY   API key (openai provider only)

Usage
-----
  from agent.core.llm import get_reply, build_system_prompt, LLMError
  reply = get_reply(messages)
"""

from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class LLMError(Exception):
    """Raised when the LLM backend is unavailable or returns an error."""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def get_reply(
    messages: list[dict],
    *,
    model: Optional[str] = None,
) -> str:
    """
    Send a list of OpenAI-format messages to the configured backend.

    messages format: [{"role": "user"|"assistant"|"system", "content": "..."}]

    Returns the assistant reply text.
    Raises LLMError on config or connectivity problems.
    """
    from agent.core import config as _config

    settings = _config.settings
    provider = settings.llm_provider.lower()

    if provider == "none":
        raise LLMError(
            "No LLM provider configured. "
            "Set AGENT_LLM_PROVIDER to 'ollama' or 'openai'."
        )

    resolved_model = model or settings.llm_model

    if provider == "ollama":
        return _ollama_chat(
            messages,
            model=resolved_model,
            base_url=settings.llm_base_url,
        )
    if provider == "openai":
        return _openai_chat(
            messages,
            model=resolved_model,
            base_url=settings.llm_base_url,
            api_key=settings.llm_api_key,
        )

    raise LLMError(f"Unknown LLM provider: {provider!r}. Choose 'ollama' or 'openai'.")


def is_available() -> bool:
    """Return True if an LLM provider is configured (not 'none')."""
    from agent.core import config as _config

    return _config.settings.llm_provider.lower() != "none"


def build_system_prompt(db_session) -> str:
    """
    Build a context-rich system prompt including the user's recent memory
    entries so the LLM can reference stored knowledge.
    """
    from agent.core.memory import list_memory

    memories = list_memory(db_session, limit=15)

    prompt = (
        "You are a personal work agent — an intelligent assistant with access "
        "to the user's long-term memory and document library.\n"
        "You help with tasks, answer questions, and proactively recall relevant "
        "past context when useful.\n\n"
    )

    if memories:
        lines = "\n".join(f"- {m.text}" for m in memories)
        prompt += f"Recent memory entries (use when relevant):\n{lines}\n\n"

    prompt += "Be concise, helpful, and direct. Cite specific memory when relevant."
    return prompt


# ---------------------------------------------------------------------------
# Provider implementations
# ---------------------------------------------------------------------------


def _ollama_chat(messages: list[dict], *, model: str, base_url: str) -> str:
    import httpx

    url = base_url.rstrip("/") + "/api/chat"
    try:
        resp = httpx.post(
            url,
            json={"model": model, "messages": messages, "stream": False},
            timeout=120.0,
        )
        resp.raise_for_status()
        data = resp.json()
        return data["message"]["content"]
    except httpx.ConnectError as exc:
        raise LLMError(
            f"Cannot connect to Ollama at {base_url!r}. Is it running?\n"
            "Start it with: ollama serve"
        ) from exc
    except httpx.HTTPStatusError as exc:
        raise LLMError(
            f"Ollama returned HTTP {exc.response.status_code}: {exc.response.text}"
        ) from exc
    except (KeyError, ValueError) as exc:
        raise LLMError(f"Unexpected Ollama response format: {exc}") from exc


def _openai_chat(
    messages: list[dict], *, model: str, base_url: str, api_key: str
) -> str:
    import httpx

    url = base_url.rstrip("/") + "/chat/completions"
    headers: dict[str, str] = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    try:
        resp = httpx.post(
            url,
            headers=headers,
            json={"model": model, "messages": messages},
            timeout=120.0,
        )
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]
    except httpx.ConnectError as exc:
        raise LLMError(
            f"Cannot connect to OpenAI-compatible API at {base_url!r}."
        ) from exc
    except httpx.HTTPStatusError as exc:
        raise LLMError(
            f"API returned HTTP {exc.response.status_code}: {exc.response.text}"
        ) from exc
    except (KeyError, IndexError, ValueError) as exc:
        raise LLMError(f"Unexpected API response format: {exc}") from exc
