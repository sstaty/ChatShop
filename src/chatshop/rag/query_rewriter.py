"""
Query rewriter module — semantic translation layer between user intent and retrieval.

Translates subjective or colloquial user language into headphone-specific technical
attributes and a clean semantic query string. This improves recall by reducing
dependence on embedding similarity alone.

Examples of rewrites:
    "for the gym"           → wireless sport earbuds sweat-resistant stable fit
    "music feels alive"     → warm bass emphasis high driver quality immersive sound
    "something for commute" → active noise cancellation portable long battery life
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, ConfigDict
from pydantic import Field as PydanticField

from chatshop.infra.llm_client import LLMClient


# ---------------------------------------------------------------------------
# Private Pydantic schemas — used only for structured LLM output
# ---------------------------------------------------------------------------


class _HeadphoneFilters(BaseModel):
    model_config = ConfigDict(extra="forbid")

    wireless: bool | None = None
    anc: bool | None = None
    type: Literal["over-ear", "in-ear", "open-back"] | None = None
    use_cases: Literal["travel", "office", "studio", "sport", "gaming"] | None = None
    min_battery_hours: int | None = None


class _FilterHints(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_price: float | None = None
    min_price: float | None = None
    min_rating: float | None = None
    headphone_filters: _HeadphoneFilters = PydanticField(
        default_factory=_HeadphoneFilters
    )


class _RewriteSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    semantic_query: str
    filter_hints: _FilterHints = PydanticField(default_factory=_FilterHints)
    intent_summary: str = ""


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """\
You are a semantic query rewriter for a headphone shopping assistant.

Translate the user's shopping message into a structured output with:

- semantic_query: Enriched descriptive phrase for vector similarity search.
  Write as a noun phrase — do NOT start with "Looking for", "I want", or similar.
  Expand colloquial language to headphone-specific attributes:
    "for the gym"       -> wireless sport earbuds sweat-resistant stable fit
    "music feels alive" -> warm bass high driver quality immersive sound
    "commute"           -> noise-cancelling headphones portable long battery life
  Max 60 words.

- filter_hints: Inferred constraints -- only populate when clearly evidenced:
    max_price / min_price (float) -- from budget mentions
    min_rating (float)            -- "well-rated" -> 4.0, "top-rated" -> 4.5
    headphone_filters:
      wireless (bool)          -- "wireless"/"bluetooth" -> true; "wired" -> false
      anc (bool)               -- "noise cancelling"/"ANC"/"quiet" -> true
      type (str)               -- "over-ear" | "in-ear" | "open-back"
      use_cases (str)          -- "travel" | "office" | "studio" | "sport" | "gaming"
      min_battery_hours (int)  -- "all day" -> 20; explicit hours -> that number

- intent_summary: One sentence describing what the user wants.

Use history to resolve references ("the second one", "under that budget").
Only set filters when confident.\
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

        {"max_price": 150.0, "extra_filters": {"wireless": True, "anc": True, "use_cases": "sport"}}
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

    def rewrite(self, user_message: str, history: list[dict] | None = None) -> RewrittenQuery:
        """Translate a user message into a retrieval-optimised query.

        Args:
            user_message: The raw user message for the current turn.
            history: Prior conversation turns in OpenAI message format,
                used to resolve references like "the second one" or
                "under that budget". Pass ``None`` or omit on the first turn.

        Returns:
            :class:`RewrittenQuery` with an enriched semantic query, inferred
            filter hints, and a normalised intent summary.
        """
        messages = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            *(history or []),
            {"role": "user", "content": user_message},
        ]
        raw = self._llm.complete(messages, response_format=_RewriteSchema)
        data = json.loads(raw)

        fh = data.get("filter_hints", {})
        hf = fh.pop("headphone_filters", {}) or {}
        fh["extra_filters"] = {k: v for k, v in hf.items() if v is not None}

        return RewrittenQuery(
            semantic_query=data.get("semantic_query", user_message),
            filter_hints=fh,
            intent_summary=data.get("intent_summary", ""),
        )
