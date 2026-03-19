"""
LLM client wrapper.

Centralises all LiteLLM calls so the rest of the codebase never imports
litellm directly. Makes it easy to swap providers or add logging/retries
in one place.
"""

from __future__ import annotations

from collections.abc import Iterator

from chatshop.config import settings


class LLMClient:
    """Thin wrapper around LiteLLM providing blocking and streaming completion.

    Supports any provider LiteLLM knows about (OpenAI, Anthropic, OpenRouter,
    Ollama, etc.) as well as custom OpenAI-compatible endpoints (Modal, vLLM,
    LiteLLM proxy) via ``api_base``.
    """

    def __init__(
        self,
        model: str,
        api_key: str,
        api_base: str | None = None,
    ) -> None:
        """
        Args:
            model: LiteLLM model string, e.g. ``"gpt-4o-mini"`` or
                ``"openrouter/anthropic/claude-3-5-sonnet"``.
            api_key: API key appropriate for the chosen model/provider.
            api_base: Optional custom base URL for OpenAI-compatible endpoints
                (e.g. a Modal deployment, vLLM server, or LiteLLM proxy).
                Leave ``None`` for standard provider routing.
        """
        self._model = model
        self._api_key = api_key or None  # litellm wants None, not ""
        self._api_base = api_base

    def complete(
        self,
        messages: str | list[dict],
        response_format: type | None = None,
        temperature: float = 0.2,
        metadata: dict | None = None,
    ) -> str:
        """Return the full assistant reply as a string.

        Default temperature is intentionally low (0.2) because most callers
        in this system produce structured JSON (Planner, Evaluator,
        QueryRewriter). Callers that want creative variance — e.g. response
        synthesis — should pass a higher value explicitly.

        Args:
            messages: Either a plain string (wrapped as a single user message)
                or an OpenAI-style message list, e.g.
                ``[{"role": "user", "content": "..."}]``.
            response_format: Optional Pydantic model class to request
                structured JSON output. LiteLLM passes this to the provider's
                ``response_format`` parameter. Returns raw JSON string.
            temperature: Sampling temperature. 0 = fully deterministic.

        Returns:
            The assistant content string, or a raw JSON string when
            ``response_format`` is supplied.
        """
        if isinstance(messages, str):
            messages = [{"role": "user", "content": messages}]
        kwargs: dict = dict(
            model=self._model,
            messages=messages,
            api_key=self._api_key,
            temperature=temperature,
        )
        if self._api_base:
            kwargs["api_base"] = self._api_base
        if response_format is not None:
            kwargs["response_format"] = response_format
        if metadata is not None:
            kwargs["metadata"] = metadata

        import litellm
        response = litellm.completion(**kwargs)
        return response.choices[0].message.content or ""

    def stream(
        self,
        messages: str | list[dict],
        temperature: float = 0.7,
        metadata: dict | None = None,
    ) -> Iterator[str]:
        """Yield assistant reply tokens one at a time.

        Temperature default is higher here (0.7) because streaming is used
        exclusively for response synthesis, where natural language variance
        is desirable.

        Args:
            messages: Either a plain string or an OpenAI-style message list.
            temperature: Sampling temperature.

        Yields:
            Individual text chunks as they arrive from the provider.
        """
        if isinstance(messages, str):
            messages = [{"role": "user", "content": messages}]
        kwargs: dict = dict(
            model=self._model,
            messages=messages,
            api_key=self._api_key,
            temperature=temperature,
            stream=True,
        )
        if metadata is not None:
            kwargs["metadata"] = metadata
        if self._api_base:
            kwargs["api_base"] = self._api_base

        import litellm
        response = litellm.completion(**kwargs)
        for chunk in response:
            content = getattr(chunk.choices[0].delta, "content", None)
            if content:
                yield content


def _api_key_for_model(model: str) -> str:
    """Return the appropriate API key for the given model string."""
    if model.startswith("openrouter/"):
        return settings.openrouter_api_key
    return settings.litellm_api_key


def llm_client_for(model: str) -> LLMClient:
    """Build an :class:`LLMClient` for the given LiteLLM model string.

    Picks the correct API key automatically:
    ``"openrouter/..."`` models use ``openrouter_api_key``;
    all others use ``litellm_api_key``.

    Args:
        model: Any LiteLLM model string, e.g. ``"gpt-4o-mini"``,
            ``"openrouter/openai/gpt-4o"``, or ``"ollama/llama3.2"``.
    """
    return LLMClient(model=model, api_key=_api_key_for_model(model))
