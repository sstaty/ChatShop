"""
Agent loop — orchestrates the full agentic retrieval cycle.

The loop drives a single conversation turn through up to ``max_iterations``
of plan → search → evaluate before forcing a final response. It composes the
Planner, Evaluator, HybridSearch, and LLMClient without containing any
reasoning logic itself.

Reference loop (from architecture doc):

    while not finished:
        plan = planner(history, previous_results, evaluator_feedback)

        if plan.action == "clarify":
            ask_user(plan.question)
            stop

        if plan.action == "search":
            results = hybrid_search(plan.search_plan)
            evaluation = evaluator(results, plan.intent_summary)
            evaluator_feedback = evaluation.reason
            continue

        if plan.action == "respond":
            return generate_final_answer(plan.response_strategy, results)
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
    """Current iteration count (0-based). Loop stops at ``max_iterations``."""

    history: list[dict] = field(default_factory=list)
    """Full conversation history in OpenAI message format."""

    last_results: list[Product] = field(default_factory=list)
    """Products returned by the most recent HybridSearch call."""

    evaluator_feedback: str | None = None
    """Reason string from the last EvaluatorOutput; None before first search."""

    finished: bool = False
    """Set to True when the loop should stop (respond or clarify action)."""

    last_plan: PlannerOutput | None = None
    """The PlannerOutput that caused the loop to stop (or the last search plan)."""


# ---------------------------------------------------------------------------
# AgentLoop
# ---------------------------------------------------------------------------


class AgentLoop:
    """Runs the plan → search → evaluate cycle for a single conversation turn.

    This class is the only entry point the UI layer needs to call. It wires
    together all Phase 2 modules and enforces the iteration cap.
    """

    def __init__(
        self,
        planner: Planner,
        evaluator: Evaluator,
        hybrid_search: HybridSearch,
        llm_client: LLMClient,
        max_iterations: int = 3,
    ) -> None:
        """
        Args:
            planner: Planner module instance.
            evaluator: Evaluator module instance.
            hybrid_search: HybridSearch module instance.
            llm_client: LLM client used for final response synthesis.
            max_iterations: Hard cap on search iterations before the loop
                forces a respond action regardless of evaluator verdict.
        """
        self._planner = planner
        self._evaluator = evaluator
        self._search = hybrid_search
        self._llm = llm_client
        self._conversationist = Conversationist(llm_client)
        self._max_iterations = max_iterations

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self, message: str, history: list[dict]) -> str:
        """Run the full agent loop and return the final response string.

        Args:
            message: The current user message.
            history: Prior conversation turns in OpenAI message format
                (does not include the current ``message``).

        Returns:
            The assistant's final response as a plain string.
        """
        state = self._run_loop(history + [{"role": "user", "content": message}])
        plan = state.last_plan

        if plan is not None and plan.action == "clarify":
            return plan.question

        strategy = self._resolve_strategy(plan, state.last_results)
        return self._synthesize(state, strategy, stream=False)  # type: ignore[return-value]

    def stream(self, message: str, history: list[dict]) -> Iterator[str]:
        """Run the agent loop and yield the final response token by token.

        Planning and retrieval iterations run to completion before streaming
        begins. Only the final response synthesis is streamed.

        Args:
            message: The current user message.
            history: Prior conversation turns in OpenAI message format.

        Yields:
            Individual text chunks from the response synthesis LLM call.
        """
        state = self._run_loop(history + [{"role": "user", "content": message}])
        plan = state.last_plan

        if plan is not None and plan.action == "clarify":
            yield plan.question
            return

        strategy = self._resolve_strategy(plan, state.last_results)
        yield from self._synthesize(state, strategy, stream=True)  # type: ignore[misc]

    def stream_with_trace(
        self, message: str, history: list[dict]
    ) -> Iterator[Union[TraceEvent, str]]:
        """Run the agent loop yielding :class:`TraceEvent` during planning/
        retrieval and plain ``str`` tokens during final response synthesis.

        This is the entry point for UIs that want to show a live reasoning
        panel alongside the streamed chat response.  Planning and retrieval
        run incrementally — each step emits a :class:`TraceEvent` before the
        next LLM call starts, so the UI updates while the loop is still
        running.

        Args:
            message: The current user message.
            history: Prior conversation turns in OpenAI message format.

        Yields:
            :class:`TraceEvent` instances for each reasoning step, then plain
            ``str`` chunks for the final LLM response.
        """
        yield TraceEvent("Analyzing request...")

        full_history = history + [{"role": "user", "content": message}]
        state = LoopState(history=full_history)

        while not state.finished and state.iteration < self._max_iterations:
            plan = self._planner.plan(
                history=state.history,
                previous_results=state.last_results or None,
                evaluator_feedback=state.evaluator_feedback,
            )
            state.last_plan = plan

            if plan.action == "clarify":
                yield TraceEvent("Clarifying...")
                yield plan.question
                return

            if plan.action == "respond":
                strategy = self._resolve_strategy(plan, state.last_results)
                yield TraceEvent("Generating response...")
                yield from self._synthesize(state, strategy, stream=True)  # type: ignore[misc]
                return

            # action == "search"
            sp = plan.search_plan
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

            suffix = "" if evaluation.satisfactory else " — retrying"
            yield TraceEvent(
                f"Retrieved {result.candidate_count} candidates\n"
                f"Evaluator: {evaluation.reason}{suffix}"
            )

            state.last_results = result.products
            state.evaluator_feedback = evaluation.verdict()
            state.iteration += 1

        # Iteration cap reached without a RespondAction
        strategy = self._resolve_strategy(state.last_plan, state.last_results)
        yield TraceEvent("Generating response...")
        yield from self._synthesize(state, strategy, stream=True)  # type: ignore[misc]

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _run_loop(self, full_history: list[dict]) -> LoopState:
        """Run iterations until finished or the cap is reached."""
        state = LoopState(history=full_history)
        while not state.finished and state.iteration < self._max_iterations:
            state = self._run_iteration(state)
        return state

    def _run_iteration(self, state: LoopState) -> LoopState:
        """Execute one plan → (search → evaluate)? step and return updated state.

        This method mutates a copy of ``state`` and returns it. It does not
        produce the final response string; that is handled by the caller after
        the loop exits.

        Args:
            state: Current loop state including history and previous results.

        Returns:
            Updated :class:`LoopState` with incremented iteration, new
            results, and evaluator feedback (or ``finished=True``).
        """
        plan = self._planner.plan(
            history=state.history,
            previous_results=state.last_results or None,
            evaluator_feedback=state.evaluator_feedback,
        )
        state.last_plan = plan

        if plan.action in ("clarify", "respond"):
            state.finished = True
            return state

        # action == "search"
        result = self._search.search(plan.search_plan)
        evaluation = self._evaluator.evaluate(
            intent_summary=plan.intent_summary,
            constraints=result.applied_filters,
            products=result.products,
            candidate_count=result.candidate_count,
        )

        state.last_results = result.products
        sp = plan.search_plan
        search_summary = (
            f"\n\nPrevious search that produced this result:\n"
            f'  Semantic query: "{sp.semantic_query}"\n'
            f"  Filters: {_format_filters(sp.filters)}\n"
            f"  Candidates retrieved: {result.candidate_count}"
        )
        state.evaluator_feedback = evaluation.verdict() + search_summary
        state.iteration += 1
        return state

    def _resolve_strategy(
        self,
        plan: PlannerOutput | None,
        last_results: list[Product],
    ) -> str:
        """Pick a response strategy from the plan or fall back on results."""
        from chatshop.agent.planner import RespondAction

        if isinstance(plan, RespondAction):
            return plan.response_strategy
        # Iteration cap hit without a RespondAction — pick best available strategy
        return "catalog_with_recommendation" if last_results else "no_results"

    def _synthesize(
        self,
        state: LoopState,
        strategy: str,
        *,
        stream: bool = False,
    ) -> str | Iterator[str]:
        """Delegate response synthesis to the Conversationist.

        Args:
            state: Final loop state containing history and retrieved products.
            strategy: One of the response strategy keys.
            stream: If True, return a token iterator; otherwise return a string.

        Returns:
            Full response string, or a token iterator when ``stream=True``.
        """
        return self._conversationist.synthesize(
            strategy=strategy,
            history=state.history,
            products=state.last_results,
            stream=stream,
        )
