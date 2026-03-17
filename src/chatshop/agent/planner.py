"""
Planner module — central reasoning component of the agent loop.

The Planner receives the full conversation state and decides the next action:
clarify an ambiguous request, issue a new retrieval search, or synthesise a
final response. It owns all reasoning and conversational state; retrieval
modules only produce evidence.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Literal, Union

from pydantic import BaseModel, ConfigDict
from pydantic import Field as PydanticField

from chatshop.data.models import Product
from chatshop.infra.llm_client import LLMClient
from chatshop.rag.query_rewriter import QueryRewriter


# ---------------------------------------------------------------------------
# Search plan types
# ---------------------------------------------------------------------------


@dataclass
class SearchFilters:
    """Structured metadata constraints derived from the user's request.

    All fields are optional — only populated when the planner has enough
    evidence to apply that constraint without over-filtering.

    Universal fields (price, rating) are typed. Domain-specific attributes
    (e.g. wireless, ANC for headphones; screen size for laptops) go into
    ``extra_filters`` so the schema stays valid across product categories.
    """

    max_price: float | None = None
    min_price: float | None = None
    min_rating: float | None = None
    extra_filters: dict[str, Any] = field(default_factory=dict)
    """Free-form domain-specific metadata constraints.

    Keys must match ChromaDB metadata field names on the ingested products.

    Examples::

        {"wireless": True, "anc": True, "type": "over-ear", "use_cases": "sport"}
    """


@dataclass
class SearchPlan:
    """Complete retrieval specification produced by the Planner."""

    semantic_query: str
    """Natural-language query sent to the vector similarity search."""

    filters: SearchFilters = field(default_factory=SearchFilters)
    """Hard metadata constraints applied before vector search."""

    sort_by: Literal["rating", "price_asc", "price_desc"] | None = None
    """Optional post-vector re-sort applied within the already-ranked result set.

    Cosine similarity ranking runs first; ``sort_by`` then re-orders within
    that semantically relevant set. Use only when the user explicitly requests
    an ordering (e.g. "cheapest ones under $100", "highest rated option").
    Leave ``None`` to preserve the vector similarity order.
    """


# ---------------------------------------------------------------------------
# Planner output — discriminated union
# ---------------------------------------------------------------------------


@dataclass
class ClarifyAction:
    """Planner decided to ask the user a clarifying question."""

    action: Literal["clarify"]
    question: str
    """The single focused question to present to the user."""
    reasoning_trace: str
    """Internal chain-of-thought explaining why clarification is needed."""


@dataclass
class SearchAction:
    """Planner decided to issue a retrieval search."""

    action: Literal["search"]
    search_plan: SearchPlan
    """Full retrieval specification to pass to HybridSearch."""
    reasoning_trace: str
    """Internal chain-of-thought explaining the retrieval strategy."""


@dataclass
class RespondAction:
    """Planner decided that current evidence is sufficient to reply."""

    action: Literal["respond"]
    response_strategy: Literal[
        "catalog_with_recommendation",
        "tradeoff_explanation",
        "no_results",
        "informational",
    ]
    """Controls the tone and structure of the response synthesis prompt.

    ``catalog_with_recommendation``
        Present 3–5 retrieved products; call out one top pick with reasoning.
    ``tradeoff_explanation``
        Compare 2–3 options head-to-head; explain when to choose each.
    ``no_results``
        No products survived filtering even after retries; tell the user why
        and suggest how to broaden the search.
    ``informational``
        Answer a conversational or educational query (e.g. "what is ANC?")
        without presenting a product catalog. Planner skips retrieval entirely.
    """
    reasoning_trace: str
    """Internal chain-of-thought explaining why this response strategy fits."""


PlannerOutput = Union[ClarifyAction, SearchAction, RespondAction]
"""Discriminated union of all possible Planner decisions."""


# ---------------------------------------------------------------------------
# Private Pydantic schema — used only for structured LLM output
# ---------------------------------------------------------------------------


class _PlannerSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: Literal["clarify", "search", "respond"]
    reasoning_trace: str
    question: str | None = None
    response_strategy: Literal[
        "catalog_with_recommendation",
        "tradeoff_explanation",
        "no_results",
        "informational",
    ] | None = None


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """\
You are the planning agent for a headphone shopping assistant. Your only job
is to decide the next action. You do NOT build search queries or rank products.

Decide one of three actions:

clarify
  The user's intent is too vague to search meaningfully — no product attributes
  or use-case can be inferred (e.g. bare "headphones" with no other context).
  Set `question` to a single focused question that resolves the ambiguity.
  Do NOT clarify if you can make a reasonable search; prefer searching.

search
  The intent is clear but results are missing or the evaluator says they are
  unsatisfactory. The search query will be built separately — you only decide
  that a search should happen.

respond
  Sufficient evidence exists to answer the user. Choose a response_strategy:
    catalog_with_recommendation  — present 3–5 products, highlight one top pick
    tradeoff_explanation         — compare 2–3 options head-to-head
    no_results                   — nothing matched even after retries; explain why
    informational                — educational/conversational query, no products needed

Rules:
- Always write reasoning_trace before deciding action.
- If retrieved products exist and evaluator feedback is positive → respond.
- If retrieved products exist but evaluator feedback is negative → search again.
- If evaluator feedback has signalled failure multiple times → respond with no_results.
- If the query is clearly informational (e.g. "what is ANC?") → respond with informational immediately.
- Prefer search over clarify whenever a reasonable query can be inferred.\
"""


# ---------------------------------------------------------------------------
# Planner class
# ---------------------------------------------------------------------------


class Planner:
    """Decides the next action given the full conversation state.

    The Planner is the sole owner of reasoning and flow control. It never
    ranks products or produces the final user-facing answer directly.
    """

    def __init__(self, llm_client: LLMClient, query_rewriter: QueryRewriter) -> None:
        """
        Args:
            llm_client: Shared LLM client used to call the planning prompt.
            query_rewriter: Used to build the SearchPlan when action is ``search``.
        """
        self._llm = llm_client
        self._rewriter = query_rewriter

    def plan(
        self,
        history: list[dict],
        previous_results: list[Product] | None = None,
        evaluator_feedback: str | None = None,
    ) -> PlannerOutput:
        """Produce the next action for the agent loop.

        Args:
            history: Full conversation history in OpenAI message format,
                including the current user turn as the last entry.
            previous_results: Products returned by the most recent retrieval
                iteration, or ``None`` on the first call.
            evaluator_feedback: The ``reason`` string from the Evaluator's
                previous output, injected so the Planner can refine its
                next search strategy. ``None`` on the first call.

        Returns:
            A :class:`ClarifyAction`, :class:`SearchAction`, or
            :class:`RespondAction` depending on what the Planner decides.
        """
        if isinstance(history, str):
            history = [{"role": "user", "content": history}]

        messages: list[dict] = [{"role": "system", "content": _SYSTEM_PROMPT}]

        if previous_results:
            context_block = "\n\n---\n\n".join(
                p.to_context_text() for p in previous_results
            )
            messages.append({
                "role": "system",
                "content": f"## Retrieved products (most recent search)\n\n{context_block}",
            })

        if evaluator_feedback:
            messages.append({
                "role": "system",
                "content": f"## Evaluator feedback\n{evaluator_feedback}",
            })

        messages.extend(history)

        raw = self._llm.complete(messages, response_format=_PlannerSchema)
        data = json.loads(raw)

        action = data["action"]
        trace = data.get("reasoning_trace", "")

        if action == "clarify":
            return ClarifyAction(
                action="clarify",
                question=data["question"],
                reasoning_trace=trace,
            )

        if action == "search":
            # QueryRewriter.rewrite() takes (user_message, history) separately.
            # history[:-1] are all prior turns; the rewriter reassembles them with
            # the current message internally, preserving full conversational context
            # for reference resolution ("the second one", "under that budget", etc.).
            last_user_msg = next(
                (m["content"] for m in reversed(history) if m["role"] == "user"), ""
            )
            rewritten = self._rewriter.rewrite(last_user_msg, history=history[:-1])
            fh = rewritten.filter_hints
            filters = SearchFilters(
                max_price=fh.get("max_price"),
                min_price=fh.get("min_price"),
                min_rating=fh.get("min_rating"),
                extra_filters=fh.get("extra_filters", {}),
            )
            return SearchAction(
                action="search",
                search_plan=SearchPlan(
                    semantic_query=rewritten.semantic_query,
                    filters=filters,
                    sort_by=None,
                ),
                reasoning_trace=trace,
            )

        # respond
        return RespondAction(
            action="respond",
            response_strategy=data["response_strategy"],
            reasoning_trace=trace,
        )
