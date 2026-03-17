"""
Agent loop — orchestrates the full agentic retrieval cycle.

The loop drives a single conversation turn through up to ``max_iterations``
of plan → search → evaluate before forcing a final response. It composes the
Planner, Evaluator, HybridSearch, and QueryRewriter without containing any
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

if TYPE_CHECKING:
    from chatshop.agent.evaluator import Evaluator, EvaluatorOutput
    from chatshop.agent.planner import Planner, PlannerOutput
    from chatshop.rag.query_rewriter import QueryRewriter
    from chatshop.rag.hybrid_search import HybridSearch


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
        query_rewriter: QueryRewriter,
        max_iterations: int = 3,
    ) -> None:
        """
        Args:
            planner: Planner module instance.
            evaluator: Evaluator module instance.
            hybrid_search: HybridSearch module instance.
            query_rewriter: QueryRewriter module instance.
            max_iterations: Hard cap on search iterations before the loop
                forces a respond action regardless of evaluator verdict.
        """
        ...

    def run(self, message: str, history: list[dict]) -> str:
        """Run the full agent loop and return the final response string.

        Args:
            message: The current user message.
            history: Prior conversation turns in OpenAI message format
                (does not include the current ``message``).

        Returns:
            The assistant's final response as a plain string.
        """
        ...

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
        ...

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
        ...
