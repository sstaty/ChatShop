"""
Agent loop — orchestrates the full agentic retrieval cycle.

The loop drives a single conversation turn through up to ``max_iterations``
of plan → search → evaluate before forcing a final response. It composes the
Planner, Evaluator, HybridSearch, and LLMClient without containing any
reasoning logic itself.

Reference loop:

    while not finished:
        plan = planner(history, previous_results, evaluator_feedback)

        if plan.action == "clarify":
            ask_user(plan.question)
            stop

        if plan.action == "respond":
            return synthesize(plan.response_strategy, results)

        if plan.action == "search":
            results = hybrid_search(plan.search_plan)
            evaluation = evaluator(results, plan.intent_summary)
            if evaluation.satisfactory:
                return synthesize("catalog_with_recommendation", results)
            evaluator_feedback = evaluation.reason
            continue
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Iterator, Union

from chatshop.agent.conversationist import Conversationist
from chatshop.agent.planner import SearchFilters
from chatshop.data.models import Product

if TYPE_CHECKING:
    from chatshop.agent.evaluator import Evaluator
    from chatshop.agent.planner import Planner, PlannerOutput
    from chatshop.rag.hybrid_search import HybridSearch
    from chatshop.infra.llm_client import LLMClient


# ---------------------------------------------------------------------------
# Reasoning trace
# ---------------------------------------------------------------------------


@dataclass
class TraceEvent:
    """A human-readable reasoning trace line emitted during the agent loop.

    Yielded by :meth:`AgentLoop.stream_with_trace` interleaved with response
    tokens so the UI can update a reasoning panel in real time.
    """

    text: str


def _format_filters(filters: SearchFilters) -> str:
    """Return a compact human-readable summary of active search filters."""
    parts: list[str] = []
    if filters.max_price is not None:
        parts.append(f"price ≤ ${filters.max_price:.0f}")
    if filters.min_price is not None:
        parts.append(f"price ≥ ${filters.min_price:.0f}")
    if filters.min_rating is not None:
        parts.append(f"rating ≥ {filters.min_rating}")
    for k, v in filters.extra_filters.items():
        parts.append(f"{k}={v}")
    return " · ".join(parts) if parts else "none"


# ---------------------------------------------------------------------------
# Loop state
# ---------------------------------------------------------------------------


@dataclass
class LoopState:
    """Mutable state carried across iterations of the agent loop."""

    iteration: int = 0
    history: list[dict] = field(default_factory=list)
    last_results: list[Product] = field(default_factory=list)
    evaluator_feedback: str | None = None
    last_plan: PlannerOutput | None = None


# ---------------------------------------------------------------------------
# AgentLoop
# ---------------------------------------------------------------------------


class AgentLoop:
    """Runs the plan → search → evaluate cycle for a single conversation turn.

    This class is the only entry point the UI layer needs to call. It wires
    together all Phase 2 modules and enforces the iteration cap.

    ``stream_with_trace`` is the canonical loop implementation. ``run`` and
    ``stream`` are thin wrappers that discard :class:`TraceEvent` items.
    """

    def __init__(
        self,
        planner: Planner,
        evaluator: Evaluator,
        hybrid_search: HybridSearch,
        llm_client: LLMClient,
        max_iterations: int = 3,
    ) -> None:
        self._planner = planner
        self._evaluator = evaluator
        self._search = hybrid_search
        self._conversationist = Conversationist(llm_client)
        self._max_iterations = max_iterations

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self, message: str, history: list[dict]) -> str:
        """Run the full agent loop and return the final response string."""
        return "".join(self.stream(message, history))

    def stream(self, message: str, history: list[dict]) -> Iterator[str]:
        """Run the agent loop and yield the final response token by token."""
        for event in self.stream_with_trace(message, history):
            if not isinstance(event, TraceEvent):
                yield event

    def stream_with_trace(
        self, message: str, history: list[dict]
    ) -> Iterator[Union[TraceEvent, str]]:
        """Run the agent loop yielding :class:`TraceEvent` during planning/
        retrieval and plain ``str`` tokens during final response synthesis.

        This is the canonical loop implementation and the entry point for UIs
        that want to show a live reasoning panel alongside the streamed response.

        Yields:
            :class:`TraceEvent` instances for each reasoning step, then plain
            ``str`` chunks for the final LLM response.
        """
        yield TraceEvent("Analyzing request...")

        state = LoopState(history=history + [{"role": "user", "content": message}])

        while state.iteration < self._max_iterations:
            plan = self._planner.plan(
                history=state.history,
                previous_results=state.last_results or None,
                evaluator_feedback=state.evaluator_feedback,
            )
            state.last_plan = plan

            if plan.action == "clarify":
                yield TraceEvent("Clarifying...")
                yield from self._conversationist.clarify(plan.question, state.history, stream=True)  # type: ignore[misc]
                return

            if plan.action == "respond":
                yield TraceEvent("Generating response...")
                yield from self._conversationist.synthesize(plan.response_strategy, state.history, state.last_results, stream=True)  # type: ignore[misc]
                return

            # action == "search"
            sp = plan.search_plan

            # Hard filter relaxation: if the previous search returned 0 candidates,
            # drop domain-specific extra_filters (type, anc, wireless) before retrying.
            # max_price is user-stated and kept. This is enforced in code, not via prompt,
            # because LLMs reliably re-apply explicit user constraints on retries.
            if not state.last_results and state.evaluator_feedback is not None:
                sp.filters.extra_filters = {}

            yield TraceEvent(
                f"Intent: {plan.intent_summary}\n"
                f'Semantic: "{sp.semantic_query}"\n'
                f"Filters: {_format_filters(sp.filters)}"
            )

            result = self._search.search(sp)
            evaluation = self._evaluator.evaluate(
                intent_summary=plan.intent_summary,
                constraints=result.applied_filters,
                products=result.products,
                candidate_count=result.candidate_count,
            )

            verdict = "Satisfactory" if evaluation.satisfactory else "Not satisfactory — retrying"
            yield TraceEvent(
                f"Retrieved {result.candidate_count} candidates\n"
                f"Evaluator: {verdict}"
            )

            state.last_results = result.products
            state.evaluator_feedback = (
                evaluation.verdict()
                + f"\n\nPrevious search:"
                + f'\n  Semantic: "{sp.semantic_query}"'
                + f"\n  Filters: {_format_filters(sp.filters)}"
                + f"\n  Candidates retrieved: {result.candidate_count}"
            )
            state.iteration += 1

            if evaluation.satisfactory:
                yield TraceEvent("Generating response...")
                yield from self._conversationist.synthesize("catalog_with_recommendation", state.history, state.last_results, stream=True)  # type: ignore[misc]
                return

        # Iteration cap reached — respond with whatever we have
        strategy = "catalog_with_recommendation" if state.last_results else "no_results"
        yield TraceEvent("Generating response...")
        yield from self._conversationist.synthesize(strategy, state.history, state.last_results, stream=True)  # type: ignore[misc]
