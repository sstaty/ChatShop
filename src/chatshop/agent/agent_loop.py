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
from typing import TYPE_CHECKING, Iterator

from chatshop.data.models import Product
from chatshop.rag.prompt import SYSTEM_PROMPT, build_user_message

if TYPE_CHECKING:
    from chatshop.agent.evaluator import Evaluator
    from chatshop.agent.planner import Planner, PlannerOutput
    from chatshop.rag.hybrid_search import HybridSearch
    from chatshop.infra.llm_client import LLMClient


# ---------------------------------------------------------------------------
# Response synthesis — strategy-specific instructions appended to SYSTEM_PROMPT
# ---------------------------------------------------------------------------

_STRATEGY_INSTRUCTIONS: dict[str, str] = {
    "catalog_with_recommendation": (
        "Present 3–5 products from the catalog. Lead with your single top recommendation "
        "and explain concisely why it fits best. Then list alternatives with key specs and prices."
    ),
    "tradeoff_explanation": (
        "Compare 2–3 of the retrieved options head-to-head. "
        "For each, explain clearly when a user should choose it over the others."
    ),
    "no_results": (
        "No products matched the user's requirements even after multiple search attempts. "
        "Explain specifically why (mention the constraints that caused the issue) "
        "and suggest how the user might broaden or adjust their search."
    ),
    "informational": (
        "Answer the user's question directly and conversationally. "
        "Do not present a product catalog unless it naturally adds value."
    ),
}


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
        state.evaluator_feedback = evaluation.verdict()
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
        """Build synthesis messages and call the LLM.

        Args:
            state: Final loop state containing history and retrieved products.
            strategy: One of the four response strategy keys.
            stream: If True, return a token iterator; otherwise return a string.

        Returns:
            Full response string, or a token iterator when ``stream=True``.
        """
        system_content = SYSTEM_PROMPT + "\n\n" + _STRATEGY_INSTRUCTIONS[strategy]
        messages: list[dict] = [{"role": "system", "content": system_content}]

        # Inject prior turns (all except the current user message)
        messages.extend(state.history[:-1])

        # Final user turn — embed the product catalog
        last_user_content = state.history[-1]["content"]
        messages.append({
            "role": "user",
            "content": build_user_message(last_user_content, state.last_results),
        })

        if stream:
            return self._llm.stream(messages)
        return self._llm.complete(messages, temperature=0.7)
