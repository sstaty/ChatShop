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

from dataclasses import dataclass, field

from chatshop.infra.llm_client import LLMClient


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

        {"wireless": True, "max_price": 150.0, "use_case": "sport"}
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
        ...

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
        ...
