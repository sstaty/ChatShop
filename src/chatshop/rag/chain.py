from collections.abc import Iterator

import litellm

from chatshop.config import settings
from chatshop.rag.prompt import SYSTEM_PROMPT, build_user_message
from chatshop.rag.retriever import Retriever


class RAGChain:
    """Orchestrates retrieval → prompt construction → LLM generation."""

    def __init__(self, retriever: Retriever | None = None) -> None:
        self._retriever = retriever or Retriever()

    # ── Public API ────────────────────────────────────────────────────────────

    def run(self, query: str) -> str:
        """Blocking call — returns the full LLM response as a string."""
        messages = self._build_messages(query)
        response = litellm.completion(
            model=settings.litellm_model,
            messages=messages,
            api_key=self._api_key(),
        )
        return response.choices[0].message.content or ""

    def stream(self, query: str) -> Iterator[str]:
        """Yield response tokens as they arrive from the LLM."""
        messages = self._build_messages(query)
        response = litellm.completion(
            model=settings.litellm_model,
            messages=messages,
            api_key=self._api_key(),
            stream=True,
        )
        for chunk in response:
            delta = chunk.choices[0].delta
            content = getattr(delta, "content", None)
            if content:
                yield content

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _api_key() -> str | None:
        """Pick the right API key based on the configured model.

        OpenRouter models are prefixed "openrouter/…" and need the OpenRouter key.
        Everything else falls back to the generic litellm_api_key.
        """
        if settings.litellm_model.startswith("openrouter/"):
            return settings.openrouter_api_key or None
        return settings.litellm_api_key or None

    def _build_messages(self, query: str) -> list[dict]:
        products = self._retriever.retrieve(query)
        user_content = build_user_message(query, products)
        return [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ]
