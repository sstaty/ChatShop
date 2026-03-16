"""
LLM client wrapper.

Centralises all LiteLLM calls so the rest of the codebase never imports
litellm directly. Makes it easy to swap providers or add logging/retries
in one place.
"""

from __future__ import annotations

from typing import Iterator


class LLMClient:
    """Thin wrapper around LiteLLM providing blocking and streaming completion."""

    def __init__(self, model: str, api_key: str) -> None:
        """
        Args:
            model: LiteLLM model string, e.g. ``"gpt-4o-mini"`` or
                ``"openrouter/anthropic/claude-3-5-sonnet"``.
            api_key: API key appropriate for the chosen model/provider.
        """
        ...

    def complete(
        self,
        messages: list[dict],
        response_format: type | None = None,
        temperature: float = 0.7,
    ) -> str:
        """Return the full assistant reply as a string.

        Args:
            messages: OpenAI-style message list, e.g.
                ``[{"role": "user", "content": "..."}]``.
            response_format: Optional Pydantic model class to request
                structured JSON output via the provider's response_format
                parameter.
            temperature: Sampling temperature (0 = deterministic).

        Returns:
            The assistant content string, or a raw JSON string when
            ``response_format`` is supplied.
        """
        ...

    def stream(self, messages: list[dict]) -> Iterator[str]:
        """Yield assistant reply tokens one at a time.

        Args:
            messages: OpenAI-style message list.

        Yields:
            Individual text chunks as they arrive from the provider.
        """
        ...
