# DEPRECATED — Phase 1 orchestration layer.
# Superseded by AgentLoop (src/chatshop/agent/agent_loop.py).
# Will be deleted when gradio_app.py is wired to AgentLoop (Phase 2 UI task).

from collections.abc import Iterator
from dataclasses import dataclass

import litellm

from chatshop.config import settings
from chatshop.data.models import Product
from chatshop.rag.prompt import SYSTEM_PROMPT, build_user_message
from chatshop.rag.retriever import Retriever


@dataclass
class SearchPlan:
    query: str
    where: dict | None
    reasoning: str


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

    def think(self, message: str, history: list[dict]) -> SearchPlan:
        """Determine how to search for the user's message.

        Currently a pass-through; later will use LLM-based query reformulation,
        filter extraction, and history-aware rewriting.
        """
        return SearchPlan(
            query=message,
            where=None,
            reasoning=f'Direct search: "{message}"',
        )

    def retrieve_and_stream(
        self, message: str, history: list[dict]
    ) -> tuple[str, Iterator[str]]:
        """Return (retrieval_info, token_iterator) for the given message."""
        plan = self.think(message, history)
        products = self._retriever.retrieve(plan.query)
        info = self._format_retrieval_info(plan, products)
        messages = self._build_messages_from_products(message, products)
        stream = self._stream_messages(messages)
        return info, stream

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

    @staticmethod
    def _format_retrieval_info(plan: SearchPlan, products: list[Product]) -> str:
        lines = [
            plan.reasoning,
            f"Retrieved: {len(products)} products",
        ]
        for i, p in enumerate(products, 1):
            price = f"${p.price:.2f}" if p.price is not None else "N/A"
            rating = f"★{p.rating:.1f}" if p.rating is not None else ""
            lines.append(f"{i}. {p.title} — {price} {rating}".rstrip())
        return "\n".join(lines)

    def _build_messages(self, query: str) -> list[dict]:
        products = self._retriever.retrieve(query)
        return self._build_messages_from_products(query, products)

    def _build_messages_from_products(
        self, query: str, products: list[Product]
    ) -> list[dict]:
        user_content = build_user_message(query, products)
        return [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ]

    def _stream_messages(self, messages: list[dict]) -> Iterator[str]:
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
