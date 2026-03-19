"""
LLM client wrapper.

Centralises all OpenAI SDK calls so the rest of the codebase never imports
openai directly.  Supports OpenAI and any OpenAI-compatible provider
(OpenRouter, Ollama, vLLM, etc.) via ``base_url``.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

from openai import OpenAI

from chatshop.config import settings
from chatshop.infra.observability import log_generation


_OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


class LLMClient:
    """Thin wrapper around the OpenAI SDK providing blocking and streaming completion.

    Supports OpenAI directly and any OpenAI-compatible endpoint (OpenRouter,
    Ollama, vLLM, Modal, etc.) via ``base_url``.
    """

    def __init__(
        self,
        model: str,
        api_key: str,
        base_url: str | None = None,
    ) -> None:
        self._model = model
        self._client = OpenAI(
            api_key=api_key or None,
            base_url=base_url,
        )

    def complete(
        self,
        messages: str | list[dict],
        response_format: type | None = None,
        temperature: float = 0.2,
        metadata: dict | None = None,
    ) -> str:
        """Return the full assistant reply as a string.

        Args:
            messages: Either a plain string (wrapped as a single user message)
                or an OpenAI-style message list.
            response_format: Optional Pydantic model class to request
                structured JSON output.
            temperature: Sampling temperature. 0 = fully deterministic.
            metadata: Optional observability dict with ``trace`` and
                ``generation_name`` keys for Langfuse logging.

        Returns:
            The assistant content string, or a raw JSON string when
            ``response_format`` is supplied.
        """
        if isinstance(messages, str):
            messages = [{"role": "user", "content": messages}]

        kwargs: dict[str, Any] = dict(
            model=self._model,
            messages=messages,
            temperature=temperature,
        )

        if response_format is not None:
            kwargs["response_format"] = _build_response_format(response_format)

        response = self._client.chat.completions.create(**kwargs)
        content = response.choices[0].message.content or ""

        # Log generation to Langfuse if trace context provided
        if metadata and metadata.get("trace"):
            log_generation(
                parent=metadata["trace"],
                name=metadata.get("generation_name", "completion"),
                model=self._model,
                input=messages,
                output=content,
                usage=_extract_usage(response),
            )

        return content

    def stream(
        self,
        messages: str | list[dict],
        temperature: float = 0.7,
        metadata: dict | None = None,
    ) -> Iterator[str]:
        """Yield assistant reply tokens one at a time.

        Args:
            messages: Either a plain string or an OpenAI-style message list.
            temperature: Sampling temperature.
            metadata: Optional observability dict for Langfuse logging.

        Yields:
            Individual text chunks as they arrive from the provider.
        """
        if isinstance(messages, str):
            messages = [{"role": "user", "content": messages}]

        kwargs: dict[str, Any] = dict(
            model=self._model,
            messages=messages,
            temperature=temperature,
            stream=True,
            stream_options={"include_usage": True},
        )

        response = self._client.chat.completions.create(**kwargs)
        collected: list[str] = []
        usage: dict[str, int] = {}

        for chunk in response:
            if chunk.usage:
                usage = _extract_usage(chunk)
            if chunk.choices:
                content = chunk.choices[0].delta.content
                if content:
                    collected.append(content)
                    yield content

        # Log full generation to Langfuse after streaming completes
        if metadata and metadata.get("trace"):
            log_generation(
                parent=metadata["trace"],
                name=metadata.get("generation_name", "stream"),
                model=self._model,
                input=messages,
                output="".join(collected),
                usage=usage,
            )


def _build_response_format(pydantic_model: type) -> dict:
    """Convert a Pydantic model class to an OpenAI json_schema response_format."""
    return {
        "type": "json_schema",
        "json_schema": {
            "name": pydantic_model.__name__,
            "schema": pydantic_model.model_json_schema(),
            "strict": False,
        },
    }


def _extract_usage(response: Any) -> dict[str, int]:
    """Pull token counts from an OpenAI response/chunk."""
    if not response.usage:
        return {}
    return {
        "prompt_tokens": response.usage.prompt_tokens or 0,
        "completion_tokens": response.usage.completion_tokens or 0,
        "total_tokens": response.usage.total_tokens or 0,
    }


def _api_key_for_model(model: str) -> str:
    """Return the appropriate API key for the given model string."""
    if model.startswith("openrouter/"):
        return settings.openrouter_api_key
    return settings.openai_api_key


def llm_client_for(model: str) -> LLMClient:
    """Build an :class:`LLMClient` for the given model string.

    Picks the correct API key and base URL automatically:
    ``"openrouter/..."`` models use ``openrouter_api_key`` with
    OpenRouter's base URL; all others use ``openai_api_key`` with
    the default OpenAI endpoint.
    """
    if model.startswith("openrouter/"):
        # Strip the "openrouter/" prefix — OpenRouter expects the raw model path
        actual_model = model[len("openrouter/"):]
        return LLMClient(
            model=actual_model,
            api_key=_api_key_for_model(model),
            base_url=_OPENROUTER_BASE_URL,
        )
    return LLMClient(model=model, api_key=_api_key_for_model(model))
