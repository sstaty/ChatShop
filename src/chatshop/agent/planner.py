"""
Planner module — central reasoning component of the agent loop.

The Planner receives the full conversation state and decides the next action:
clarify an ambiguous request, issue a new retrieval search, or synthesise a
final response. It owns all reasoning and conversational state; retrieval
modules only produce evidence.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Literal, Union

from pydantic import BaseModel, ConfigDict
from pydantic import Field as PydanticField

from chatshop.data.models import Product
from chatshop.infra.llm_client import LLMClient
from chatshop.rag.query_rewriter import QueryRewriter

logger = logging.getLogger(__name__)


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
    intent_summary: str = ""
    """Normalised user intent from QueryRewriter; forwarded to the Evaluator by AgentLoop."""


@dataclass
class RespondAction:
    """Planner decided that current evidence is sufficient to reply."""

    action: Literal["respond"]
    response_strategy: Literal[
        "catalog_with_recommendation",
        "tradeoff_explanation",
        "narrow_results",
        "no_results",
        "informational",
        "off_topic",
    ]
    """Controls the tone and structure of the response synthesis prompt.

    ``catalog_with_recommendation``
        Present 3–5 retrieved products; call out one top pick with reasoning.
    ``tradeoff_explanation``
        Compare 2–3 options head-to-head; explain when to choose each.
    ``narrow_results``
        Only 1–2 products match; present them clearly and offer to broaden.
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


def strategy_for_result_count(count: int) -> str:
    """Map a result count to the appropriate response strategy.

    Used by the Planner's deterministic post-search routing and by the
    AgentLoop's iteration-cap fallback to keep thresholds in one place.
    """
    if count == 0:
        return "no_results"
    if count <= 2:
        return "narrow_results"
    return "catalog_with_recommendation"


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
        "narrow_results",
        "no_results",
        "informational",
        "off_topic",
    ] | None = None


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """\
You are the planning agent for a personal audio shopping assistant specialising in
headphones and earbuds.
Your only job is to decide the next action. You do NOT build search queries or rank products.

The catalog covers all personal audio worn on or in the ears:
  over-ear headphones, on-ear headphones, in-ear earbuds.

Decide one of three actions:

clarify
  The user's query is missing critical context that would significantly change
  which products to retrieve — specifically both budget AND form factor/type
  are completely absent. Ask ONE focused question covering the most important
  missing pieces.

  Examples requiring clarification:
    "headphones for running"  → no budget, no type → ask budget + type preference
    "i need new earbuds"      → no use case, no budget → ask use case + budget
    "something for the gym"   → no budget, no type → ask budget + preference (earbuds vs headphones)

  Do NOT clarify if:
    - The user has already mentioned a budget (even approximate), OR
    - The use case strongly implies a form factor (e.g. "ANC for flights" → over-ear implied,
      "running" → in-ear/TWS implied)
    - The query is clearly informational ("what is ANC?") → use respond/informational instead
    - The query is off-topic or a greeting → use respond/off_topic instead

search
  ONLY when evaluator_feedback is absent — meaning no search has been run yet this turn.
  If evaluator_feedback is present, you have already searched. Do NOT search again.

respond
  Sufficient evidence exists to answer the user without a retrieval search. Choose a response_strategy:
    tradeoff_explanation         — compare 2–3 options head-to-head
    no_results                   — nothing matched; explain why and suggest how to broaden
    informational                — educational/conversational query about personal audio, no products needed
    off_topic                    — user asked about something unrelated to personal audio, or sent a greeting

When evaluator_feedback is present:
  → The search returned 0 results. The query is over-constrained. Choose clarify.
  → Write one focused question naming the filters that were applied and asking
    which constraint the user would prefer to relax.
  → Example: "No over-ear headphones under $50 — closest options start around $70.
    Stretch the budget, or would on-ear or earbuds work?"

Rules:
- Always write reasoning_trace before deciding action.
- If the query is clearly informational about audio (e.g. "what is ANC?", "what does TWS mean?") → respond with informational immediately.
- If the user sends a greeting ("hey", "hi", "hello", "hey man", etc.) with no product intent → respond with off_topic immediately.
- If the user asks about a non-audio product (laptops, phones, TVs, furniture, cars, etc.) → respond with off_topic immediately.
- If the query is completely unrelated to audio → respond with off_topic immediately.
- Headphones, earbuds, in-ear monitors (IEMs), true wireless (TWS), and earphones are ALL on-topic — never route these to off_topic.
- Once the user has answered a clarifying question (budget or type provided) → search, do not clarify again.\
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
        metadata: dict | None = None,
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

        # Post-search deterministic routing — never delegate to LLM for these
        if previous_results is not None and len(previous_results) >= 1:
            return RespondAction(
                action="respond",
                response_strategy=strategy_for_result_count(len(previous_results)),
                reasoning_trace=f"{len(previous_results)} results retrieved.",
            )
        # previous_results is None or empty — fall through to LLM

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
                "content": f"## Evaluator feedback (most recent search)\n\n{evaluator_feedback}",
            })

        messages.extend(history)

        raw = ""
        try:
            raw = self._llm.complete(messages, response_format=_PlannerSchema, metadata=metadata)
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
                rewritten = self._rewriter.rewrite(history, evaluator_feedback=evaluator_feedback, metadata=metadata)
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
                    intent_summary=rewritten.intent_summary,
                )

            # respond
            return RespondAction(
                action="respond",
                response_strategy=data["response_strategy"],
                reasoning_trace=trace,
            )
        except (json.JSONDecodeError, KeyError) as exc:
            logger.warning("Planner JSON parse failed: %s — raw: %.200s", exc, raw)
            return ClarifyAction(
                action="clarify",
                question="Could you rephrase your request?",
                reasoning_trace=f"JSON parse fallback: {exc}",
            )
