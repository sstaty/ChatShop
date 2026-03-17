"""
Evaluator module — retrieval quality gate.

The Evaluator is a lightweight LLM call that scores whether the current
evidence set is sufficient to confidently answer the user's request. It does
not control agent flow; it only produces a binary verdict and a reason string
that the Planner uses on the next iteration.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict

from chatshop.data.models import Product
from chatshop.infra.llm_client import LLMClient


@dataclass
class EvaluatorOutput:
    """Result of a single evidence-sufficiency evaluation."""

    satisfactory: bool
    """True when the retrieved products are sufficient to answer the request."""

    reason: str
    """Concrete explanation of why the evidence is or is not sufficient.

    When ``satisfactory`` is False this string is injected into the next
    Planner iteration so it can refine the search strategy.
    """

    def verdict(self) -> str:
        """Return a human-readable verdict string."""
        status = "satisfactory" if self.satisfactory else "not satisfactory"
        return f"Results are {status}. {self.reason}"


# ---------------------------------------------------------------------------
# Private Pydantic schema — used only for structured LLM output
# ---------------------------------------------------------------------------


class _EvaluatorSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    satisfactory: bool
    reason: str


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """\
You are a retrieval quality judge for a headphone shopping assistant.

You are given:
- The user's intent (one sentence)
- The active search constraints (price, features, etc.)
- The number of products that passed the metadata filter (candidate_count)
- The retrieved products

Decide whether the evidence is sufficient to answer the user confidently.

satisfactory: true  — enough relevant products exist that match the intent and constraints.
satisfactory: false — when any of these apply:
  - candidate_count < 3 (over-filtering; results may be incomplete)
  - products clearly don't match the stated intent
  - key constraints (price ceiling, product type) are violated in most results

reason: one concrete sentence. When false, be specific about what is missing
or wrong so the Planner can act on it (e.g. "All results exceed the $120 budget"
or "No wireless options found — try relaxing the type filter").\
"""


# ---------------------------------------------------------------------------
# Evaluator class
# ---------------------------------------------------------------------------


class Evaluator:
    """Judges whether retrieved evidence is good enough to answer the user.

    Runs at low temperature with a binary-decision prompt to minimise
    hallucination and enforce consistent structured output.
    """

    def __init__(self, llm_client: LLMClient) -> None:
        """
        Args:
            llm_client: Shared LLM client. Should be configured with low
                temperature (≤ 0.2) for deterministic evaluation.
        """
        self._llm = llm_client

    def evaluate(
        self,
        intent_summary: str,
        constraints: dict,
        products: list[Product],
        candidate_count: int,
    ) -> EvaluatorOutput:
        """Score the sufficiency of a retrieval result set.

        Args:
            intent_summary: A normalised one-sentence description of what
                the user is trying to find. Produced by the QueryRewriter.
            constraints: The active filters (price, rating, etc.) that were
                applied during retrieval, so the evaluator can check
                constraint satisfaction.
            products: Top-N products returned by HybridSearch.
            candidate_count: Total number of products that passed the metadata
                filter before vector ranking. Very small values (< 3) should
                bias the evaluator toward ``satisfactory=False``.

        Returns:
            :class:`EvaluatorOutput` with a binary verdict and a concrete
            reason string.
        """
        if not products:
            return EvaluatorOutput(
                satisfactory=False,
                reason="No products were retrieved. The filters may be too restrictive.",
            )

        product_block = "\n\n---\n\n".join(p.to_context_text() for p in products)

        messages = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": (
                f"## User intent\n{intent_summary}\n\n"
                f"## Active constraints\n{constraints}\n\n"
                f"## Candidate count (passed filters)\n{candidate_count}\n\n"
                f"## Retrieved products\n\n{product_block}"
            )},
        ]

        raw = self._llm.complete(messages, response_format=_EvaluatorSchema)
        data = json.loads(raw)
        return EvaluatorOutput(satisfactory=data["satisfactory"], reason=data["reason"])
