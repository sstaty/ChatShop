"""
Evaluator module — retrieval quality gate.

The Evaluator diagnoses whether the current evidence set is sufficient to
answer the user's request. It produces a deterministic ``diagnosis`` (derived
from candidate_count) plus LLM-identified ``blocking_constraints`` so the
Planner can handle the situation conversationally.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, ConfigDict

from chatshop.data.models import Product
from chatshop.infra.llm_client import LLMClient

logger = logging.getLogger(__name__)


@dataclass
class EvaluatorOutput:
    """Result of a single evidence-sufficiency evaluation."""

    diagnosis: Literal["no_results", "narrow_results", "sufficient"]
    """Deterministic quality label derived from candidate_count.

    ``no_results``     — 0 candidates passed the filters; query is over-constrained.
    ``narrow_results`` — 1–2 candidates; limited but presentable.
    ``sufficient``     — 3+ candidates; enough to generate a confident response.
    """

    blocking_constraints: list[str]
    """Constraint names identified by the LLM as limiting the result set.

    E.g. ``["price", "type"]``. Empty when diagnosis is ``sufficient`` or
    when the LLM call is skipped (0 candidates).
    """

    reason: str
    """Concrete explanation of the retrieval outcome."""

    @property
    def label(self) -> str:
        """Human-readable diagnosis label for UI trace display."""
        return {
            "sufficient": "Sufficient",
            "narrow_results": "Narrow results",
            "no_results": "No results — will ask user to clarify",
        }[self.diagnosis]

    def verdict(self) -> str:
        """Return a human-readable verdict string."""
        status = "satisfactory" if self.diagnosis == "sufficient" else "not satisfactory"
        return f"Results are {status}. {self.reason}"


# ---------------------------------------------------------------------------
# Private Pydantic schema — used only for structured LLM output
# ---------------------------------------------------------------------------


class _EvaluatorSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    blocking_constraints: list[str]
    reason: str


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """\
You are a retrieval quality analyst for a headphone shopping assistant.

You are given:
- The user's intent (one sentence)
- The active search constraints (price, features, etc.)
- The number of products that passed the metadata filter (candidate_count)
- The retrieved products

Your job is to identify which constraints are limiting the result set.

blocking_constraints: list the specific constraint names that are too restrictive
  (e.g. ["price", "type"], ["max_price"], ["wireless"]).
  Use short, human-readable names matching the active constraints shown.
  Leave empty if results are plentiful (3 or more candidates) or if the
  results clearly satisfy the user's intent.

reason: one concrete sentence describing what is limiting results or confirming they are fine.
  Examples:
    "The $30 price ceiling and over-ear requirement together reduce the pool to 2 products."
    "Only 1 wireless over-ear option exists under $50 in the catalog."
    "Good selection of wireless earbuds under $100 — results look solid."\
"""


# ---------------------------------------------------------------------------
# Evaluator class
# ---------------------------------------------------------------------------


class Evaluator:
    """Diagnoses retrieval quality and identifies blocking constraints.

    ``diagnosis`` is computed deterministically from ``candidate_count``;
    ``blocking_constraints`` and ``reason`` come from a low-temperature LLM call.
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
        """Diagnose the quality of a retrieval result set.

        Args:
            intent_summary: A normalised one-sentence description of what
                the user is trying to find.
            constraints: The active filters applied during retrieval.
            products: Top-N products returned by HybridSearch.
            candidate_count: Total number of products that passed the metadata
                filter before vector ranking.

        Returns:
            :class:`EvaluatorOutput` with a deterministic diagnosis,
            LLM-identified blocking constraints, and a reason string.
        """
        # Deterministic diagnosis — no LLM needed for 0 candidates.
        if candidate_count == 0:
            return EvaluatorOutput(
                diagnosis="no_results",
                blocking_constraints=[],
                reason="No products passed the filters.",
            )

        diagnosis: Literal["narrow_results", "sufficient"] = (
            "narrow_results" if candidate_count <= 2 else "sufficient"
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

        raw = ""
        try:
            raw = self._llm.complete(messages, response_format=_EvaluatorSchema)
            data = json.loads(raw)
            return EvaluatorOutput(
                diagnosis=diagnosis,
                blocking_constraints=data["blocking_constraints"],
                reason=data["reason"],
            )
        except (json.JSONDecodeError, KeyError) as exc:
            logger.warning("Evaluator JSON parse failed: %s — raw: %.200s", exc, raw)
            return EvaluatorOutput(
                diagnosis=diagnosis,
                blocking_constraints=[],
                reason=f"Evaluator parse error: {exc}",
            )
