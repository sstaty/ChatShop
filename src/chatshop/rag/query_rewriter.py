"""
Query rewriter module — semantic translation layer between user intent and retrieval.

Translates subjective or colloquial user language into technical attributes
and a clean semantic query string. This improves recall by reducing dependence
on embedding similarity alone.

Examples of rewrites:
    "for the gym"           → stable fit, sweat resistance, wireless, sport use-case
    "music feels alive"     → bass emphasis, warm tuning, high driver quality
    "something for commute" → noise isolation or ANC, comfort, portable form factor
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from pydantic import BaseModel, Field as PydanticField

from chatshop.infra.llm_client import LLMClient


# ---------------------------------------------------------------------------
# Private Pydantic schema — used only for structured LLM output
# ---------------------------------------------------------------------------


class _FilterHints(BaseModel):
    max_price: float | None = None
    min_price: float | None = None
    min_rating: float | None = None
    extra_filters: dict = PydanticField(default_factory=dict)


class _RewriteSchema(BaseModel):
    semantic_query: str
    filter_hints: _FilterHints = PydanticField(default_factory=_FilterHints)
    intent_summary: str = ""


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """\
You are a semantic query rewriter for a product search system.

Your job: translate the user's shopping message into a structured output with:

- semantic_query: Enriched natural-language query for vector similarity search.
  Expand colloquial language to technical attributes (e.g. "for the gym" ->
  "wireless earbuds sweat-resistant secure stable fit sport use-case"). Max 60 words.

- filter_hints: Inferred metadata constraints. Only populate when confident:
    - max_price / min_price (float) -- from explicit budget mentions
    - min_rating (float) -- from quality language like "well-rated" -> 4.0
    - extra_filters (dict) -- domain-specific attrs, e.g.
      {"wireless": true, "anc": true, "use_case": "sport"}

- intent_summary: One sentence describing what the user wants (used by the
  Evaluator to judge whether results satisfy the request).

Use conversation history to resolve references like "the second one", "under that
budget", or "cheaper option". Only add filter constraints when clearly evidenced.\
"""


@dataclass
class RewrittenQuery:
    """Output of a single query rewrite operation."""

    semantic_query: str
    """Enriched natural-language query ready for vector similarity search.

    Should be more specific and technically grounded than the raw user message,
    while still being expressed in natural language for the embedding model.
    """

    filter_hints: dict = field(default_factory=dict)
    """Suggested metadata filter values inferred from the user's message.

    Keys mirror :class:`~chatshop.agent.planner.SearchFilters` field names.
    The Planner decides whether to apply these hints as hard filters.

    Example::

        {"max_price": 150.0, "extra_filters": {"wireless": True, "use_case": "sport"}}
    """

    intent_summary: str = ""
    """One-sentence normalised description of what the user is looking for.

    Passed to the Evaluator as structured context so it can judge constraint
    satisfaction without re-parsing the raw conversation history.
    """


class QueryRewriter:
    """Rewrites a user message into a structured, retrieval-optimised form.

    Runs once per user turn before the first Planner call. The Planner may
    use the ``filter_hints`` and ``intent_summary`` when constructing its
    :class:`~chatshop.agent.planner.SearchPlan`.
    """

    def __init__(self, llm_client: LLMClient) -> None:
        """
        Args:
            llm_client: Shared LLM client used for the rewrite prompt.
        """
        self._llm = llm_client

    def rewrite(self, user_message: str, history: list[dict]) -> RewrittenQuery:
        """Translate a user message into a retrieval-optimised query.

        Args:
            user_message: The raw user message for the current turn.
            history: Prior conversation turns in OpenAI message format,
                used to resolve references like "the second one" or
                "under that budget".

        Returns:
            :class:`RewrittenQuery` with an enriched semantic query, inferred
            filter hints, and a normalised intent summary.
        """
        messages = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            *history,
            {"role": "user", "content": user_message},
        ]
        raw = self._llm.complete(messages, response_format=_RewriteSchema)
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return RewrittenQuery(semantic_query=user_message)

        hints = data.get("filter_hints", {})
        return RewrittenQuery(
            semantic_query=data.get("semantic_query", user_message),
            filter_hints=hints if isinstance(hints, dict) else {},
            intent_summary=data.get("intent_summary", ""),
        )
