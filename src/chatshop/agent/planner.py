"""
Planner module — central reasoning component of the agent loop.

The Planner receives the full conversation state and decides the next action:
clarify an ambiguous request, issue a new retrieval search, or synthesise a
final response. It owns all reasoning and conversational state; retrieval
modules only produce evidence.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Union

from chatshop.data.models import Product
from chatshop.infra.llm_client import LLMClient


# ---------------------------------------------------------------------------
# Search plan types
# ---------------------------------------------------------------------------


@dataclass
class SearchFilters:
    """Structured metadata constraints derived from the user's request.

    All fields are optional — only populated when the planner has enough
    evidence to apply that constraint without over-filtering.
    """

    max_price: float | None = None
    min_price: float | None = None
    min_rating: float | None = None
    wireless: bool | None = None
    anc: bool | None = None
    waterproof: bool | None = None
    use_case: str | None = None


@dataclass
class SearchPlan:
    """Complete retrieval specification produced by the Planner."""

    semantic_query: str
    """Natural-language query sent to the vector similarity search."""

    filters: SearchFilters = field(default_factory=SearchFilters)
    """Hard metadata constraints applied before vector search."""

    sort_by: Literal["rating", "price_asc", "price_desc"] | None = None
    """Optional deterministic sort applied to the filtered candidate pool."""


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
        "final_recommendation",
        "tradeoff_explanation",
        "no_results",
        "informational",
    ]
    """Controls the tone and structure of the response synthesis prompt."""
    reasoning_trace: str
    """Internal chain-of-thought explaining why this response strategy fits."""


PlannerOutput = Union[ClarifyAction, SearchAction, RespondAction]
"""Discriminated union of all possible Planner decisions."""


# ---------------------------------------------------------------------------
# Planner class
# ---------------------------------------------------------------------------


class Planner:
    """Decides the next action given the full conversation state.

    The Planner is the sole owner of reasoning and flow control. It never
    ranks products or produces the final user-facing answer directly.
    """

    def __init__(self, llm_client: LLMClient) -> None:
        """
        Args:
            llm_client: Shared LLM client used to call the planning prompt.
        """
        ...

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
        ...
