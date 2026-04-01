"""
Curator module — post-search product selection with structured LLM output.

Runs after search + evaluate, before the conversationist. Given the raw search
results and the user's intent, it selects up to 3 products and annotates each
with a badge, rationale, and key attribute chips.
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

from pydantic import BaseModel

from chatshop.data.models import Product

if TYPE_CHECKING:
    from chatshop.infra.llm_client import LLMClient

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Output schema
# ---------------------------------------------------------------------------


class PickedProduct(BaseModel):
    product_id: str
    badge: str          # "best match" | "best value" | "luxury pick" | "hidden gem"
    rationale: str      # 1-2 sentences why this fits THIS user's intent
    key_attrs: list[str]  # 2-4 chips e.g. ["wired", "IPX5", "under $150"]


class ProductSelectionOutput(BaseModel):
    intro: str              # e.g. "Found 3 that fit perfectly."
    picks: list[PickedProduct]  # max 3


# ---------------------------------------------------------------------------
# Prompt
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """\
You are a product curator for a headphone shopping assistant.

You will be given a list of products that matched a search query, along with the
user's intent. Your job is to select the best 3 products (or fewer if less than 3
are provided) and annotate each one.

For each picked product output:
- product_id: the exact product_id from the input
- badge: one of "best match", "best value", "luxury pick", "hidden gem"
  - "best match": fits the user's stated intent most closely overall
  - "best value": best price-to-quality ratio for the use case
  - "luxury pick": premium option for users who want the best regardless of price
  - "hidden gem": lesser-known option that punches above its price or popularity
- rationale: 1-2 sentences explaining why THIS product fits THIS user's intent
- key_attrs: 2-4 short chips summarising the most relevant specs (e.g. "wireless", "IPX5", "40h battery", "under $150")

Also write a short intro sentence (e.g. "Found 3 great options for commuting under $200.").

Rules:
- Assign each picked product a different badge where possible.
- Rationale must reference the user's specific intent, not generic praise.
- key_attrs should be the 2-4 specs most relevant to the user's request.
- Only pick products from the provided list. Do not invent products.\
"""


# ---------------------------------------------------------------------------
# Curator
# ---------------------------------------------------------------------------


class Curator:
    """Selects and annotates top products using a structured LLM call."""

    def __init__(self, llm_client: LLMClient) -> None:
        self._llm = llm_client

    def curate(
        self,
        products: list[Product],
        intent_summary: str,
        history: list[dict],
        metadata: dict | None = None,
    ) -> ProductSelectionOutput:
        """Select up to 3 products and annotate them for the frontend.

        Args:
            products: Raw products from HybridSearch.
            intent_summary: Normalised user intent from the QueryRewriter.
            history: Conversation history for additional context.
            metadata: Optional observability dict for Langfuse logging.

        Returns:
            A :class:`ProductSelectionOutput` with intro and up to 3 picks.
        """
        product_lines = "\n\n".join(p.to_context_text() + f"\nproduct_id: {p.product_id}" for p in products)
        user_context = "\n".join(
            f"{m['role'].upper()}: {m['content']}"
            for m in history
            if m.get("role") in ("user", "assistant")
        )

        messages = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"## User intent\n{intent_summary}\n\n"
                    f"## Conversation context\n{user_context}\n\n"
                    f"## Available products\n{product_lines}"
                ),
            },
        ]

        raw = ""
        try:
            raw = self._llm.complete(
                messages,
                response_format=ProductSelectionOutput,
                temperature=0.3,
                metadata=metadata,
            )
            data = json.loads(raw)
            return ProductSelectionOutput.model_validate(data)
        except (json.JSONDecodeError, ValueError) as exc:
            logger.warning("Curator parse failed: %s — raw: %.200s", exc, raw)
            # Fallback: return first 3 products with minimal annotation
            picks = [
                PickedProduct(
                    product_id=p.product_id,
                    badge="recommended",
                    rationale=f"{p.title} matches your request.",
                    key_attrs=[],
                )
                for p in products[:3]
            ]
            return ProductSelectionOutput(intro="Here are some options.", picks=picks)
