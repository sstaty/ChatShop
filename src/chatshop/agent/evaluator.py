"""
Evaluator module — retrieval quality gate.

The Evaluator is a lightweight LLM call that scores whether the current
evidence set is sufficient to confidently answer the user's request. It does
not control agent flow; it only produces a binary verdict and a reason string
that the Planner uses on the next iteration.
"""

from __future__ import annotations

from dataclasses import dataclass

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
        ...

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
        ...
