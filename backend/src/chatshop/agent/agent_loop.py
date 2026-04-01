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
            evaluator_feedback = format_feedback(evaluation, search_plan)
            continue  # Planner decides respond/clarify on next iteration
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Iterator, Union

from chatshop.agent.conversationist import Conversationist
from chatshop.agent.planner import SearchFilters, strategy_for_result_count
from chatshop.api.sse_events import (
    ClarifyEvent,
    DoneEvent,
    IntentEvent,
    ProductsEvent,
    ResponseChunkEvent,
    SSEEvent,
    ThinkingEvent,
)
from chatshop.data.models import Product
from chatshop.infra.observability import (
    create_span,
    create_trace,
    end_span,
    flush_observability,
    llm_metadata,
)

if TYPE_CHECKING:
    from chatshop.agent.curator import Curator
    from chatshop.agent.evaluator import Evaluator, EvaluatorOutput
    from chatshop.agent.planner import Planner, PlannerOutput, SearchPlan
    from chatshop.rag.hybrid_search import HybridSearch, SearchResult
    from chatshop.infra.llm_client import LLMClient


# ---------------------------------------------------------------------------
# Reasoning trace
# ---------------------------------------------------------------------------


THINKING_MESSAGES: dict[str, dict[str, str]] = {
    "analyzing":  {"message": "Decoding your request...",      "detail": "figuring out what you want"},
    "searching":  {"message": "Scanning the catalogue...",     "detail": "running hybrid search"},
    "evaluating": {"message": "Checking quality...",           "detail": "evaluator quality gate"},
    "curating":   {"message": "Picking your best options...", "detail": "curator selecting top products"},
    "responding": {"message": "Crafting your answer...",       "detail": "almost there"},
    "clarifying": {"message": "Need a bit more info...",       "detail": ""},
}


def _filters_dict(filters: SearchFilters) -> dict:
    """Convert SearchFilters to a plain dict for IntentEvent."""
    d: dict = {}
    if filters.max_price is not None:
        d["max_price"] = filters.max_price
    if filters.min_price is not None:
        d["min_price"] = filters.min_price
    d.update(filters.extra_filters)
    return d


@dataclass
class AgentResult:
    """Structured output from a single agent turn, used by the eval system.

    Captures intermediate pipeline state alongside the final response so
    evals can run deterministic checks on action routing, filter extraction,
    and response strategy without re-parsing streamed output.
    """

    planner_output: PlannerOutput
    """The first planner decision for this turn (action, filters, strategy)."""

    search_results: list[Product] | None
    """Products returned by the search step, or None for clarify/respond turns."""

    evaluator_output: EvaluatorOutput | None
    """Evaluator diagnosis from the last search iteration, or None if no search ran."""

    final_response: str
    """The complete synthesized response text."""

    iterations: int
    """Number of plan→search→evaluate iterations completed before responding."""

    trace_id: str | None = None
    """Langfuse trace ID for this turn (informational)."""


# Deprecated: use typed SSEEvent types from chatshop.api.sse_events instead.
@dataclass
class TraceEvent:
    """Deprecated. Use ThinkingEvent / IntentEvent etc. from chatshop.api.sse_events."""

    text: str


def _format_filters(filters: SearchFilters) -> str:
    """Return a compact human-readable summary of active search filters."""
    parts: list[str] = []
    if filters.max_price is not None:
        parts.append(f"price ≤ ${filters.max_price:.0f}")
    if filters.min_price is not None:
        parts.append(f"price ≥ ${filters.min_price:.0f}")
    for k, v in filters.extra_filters.items():
        parts.append(f"{k}={v}")
    return " · ".join(parts) if parts else "none"


def _format_feedback(
    evaluation: "EvaluatorOutput",
    sp: "SearchPlan",
    candidate_count: int,
) -> str:
    """Format evaluator output into a feedback string for the next Planner call."""
    constraints = ", ".join(evaluation.blocking_constraints) or "unknown"
    return (
        f"Diagnosis: {evaluation.diagnosis}\n"
        f"Blocking constraints: {constraints}\n"
        f"Reason: {evaluation.reason}\n\n"
        f"Previous search:\n"
        f'  Semantic: "{sp.semantic_query}"\n'
        f"  Filters: {_format_filters(sp.filters)}\n"
        f"  Candidates retrieved: {candidate_count}"
    )


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
        curator: Curator,
        max_iterations: int = 3,
    ) -> None:
        self._planner = planner
        self._evaluator = evaluator
        self._search = hybrid_search
        self._conversationist = Conversationist(llm_client)
        self._curator = curator
        self._max_iterations = max_iterations

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self, message: str, history: list[dict]) -> str:
        """Run the full agent loop and return the final response string."""
        return "".join(self.stream(message, history))

    def run_with_result(
        self, message: str, history: list[dict], *, parent_trace: object | None = None,
    ) -> AgentResult:
        """Run the full agent loop and return a structured :class:`AgentResult`.

        Drives the same plan → search → evaluate cycle as
        :meth:`stream_with_trace` but collects intermediate state instead of
        yielding it. Used by the eval system to run deterministic checks on
        action routing, filter extraction, and response strategy.

        If *parent_trace* is provided (a Langfuse trace or span), this run is
        nested under it as a span instead of creating a new top-level trace.
        """
        if parent_trace is not None:
            trace = create_span(parent_trace, "agent_turn_eval", input={"user_message": message})
        else:
            trace = create_trace("agent_turn_eval", metadata={"user_message": message})
        trace_id: str | None = getattr(trace, "id", None)

        state = LoopState(history=history + [{"role": "user", "content": message}])
        first_plan: PlannerOutput | None = None
        last_eval: EvaluatorOutput | None = None

        while state.iteration < self._max_iterations:
            planner_span = create_span(trace, "planner", input={"iteration": state.iteration})
            plan = self._planner.plan(
                history=state.history,
                previous_results=state.last_results or None,
                evaluator_feedback=state.evaluator_feedback,
                metadata=llm_metadata(planner_span, "planner"),
            )
            end_span(planner_span, output={"action": plan.action})
            if first_plan is None:
                first_plan = plan
            state.last_plan = plan

            if plan.action == "clarify":
                conv_span = create_span(trace, "conversationist", input={"mode": "clarify"})
                response = "".join(
                    self._conversationist.clarify(plan.question, state.history, stream=True, metadata=llm_metadata(conv_span, "conversationist-clarify"))  # type: ignore[misc]
                )
                end_span(conv_span, output={"mode": "clarify"})
                if parent_trace is not None:
                    end_span(trace, output={"action": "clarify"})
                else:
                    flush_observability()
                return AgentResult(first_plan, None, None, response, state.iteration, trace_id)

            if plan.action == "respond":
                conv_span = create_span(trace, "conversationist", input={"mode": "synthesize", "strategy": plan.response_strategy})
                response = "".join(
                    self._conversationist.synthesize(  # type: ignore[misc]
                        plan.response_strategy, state.history, state.last_results, stream=True,
                        metadata=llm_metadata(conv_span, "conversationist-synthesize"),
                    )
                )
                end_span(conv_span, output={"strategy": plan.response_strategy})
                if parent_trace is not None:
                    end_span(trace, output={"action": "respond"})
                else:
                    flush_observability()
                return AgentResult(first_plan, state.last_results or None, last_eval, response, state.iteration, trace_id)

            # action == "search"
            sp = plan.search_plan
            search_span = create_span(trace, "hybrid_search", input={"semantic_query": sp.semantic_query})
            result = self._search.search(sp)
            end_span(search_span, output={"candidate_count": result.candidate_count})

            eval_span = create_span(trace, "evaluator", input={"candidate_count": result.candidate_count})
            last_eval = self._evaluator.evaluate(
                intent_summary=plan.intent_summary,
                constraints=result.applied_filters,
                products=result.products,
                candidate_count=result.candidate_count,
                metadata=llm_metadata(eval_span, "evaluator"),
            )
            end_span(eval_span, output={"diagnosis": last_eval.diagnosis})

            state.last_results = result.products
            state.evaluator_feedback = _format_feedback(last_eval, sp, result.candidate_count)
            state.iteration += 1

        # Iteration cap — respond with whatever we have
        strategy = strategy_for_result_count(len(state.last_results))
        conv_span = create_span(trace, "conversationist", input={"mode": "synthesize", "strategy": strategy})
        response = "".join(
            self._conversationist.synthesize(strategy, state.history, state.last_results, stream=True, metadata=llm_metadata(conv_span, "conversationist-synthesize"))  # type: ignore[misc]
        )
        end_span(conv_span, output={"strategy": strategy})
        if parent_trace is not None:
            end_span(trace, output={"action": "respond", "capped": True})
        else:
            flush_observability()
        return AgentResult(first_plan, state.last_results or None, last_eval, response, state.iteration, trace_id)

    def stream(self, message: str, history: list[dict]) -> Iterator[str]:
        """Run the agent loop and yield the final response token by token."""
        for event in self.stream_with_trace(message, history):
            if isinstance(event, ResponseChunkEvent):
                yield event.text

    def stream_with_trace(
        self, message: str, history: list[dict]
    ) -> Iterator[SSEEvent]:
        """Run the agent loop yielding typed SSEEvent instances.

        Yields ThinkingEvent / IntentEvent / ProductsEvent during planning and
        retrieval, then ResponseChunkEvent tokens during synthesis, and a
        DoneEvent at the end.

        Uses observability.py (langfuse) to track LLM calls, context, usage.
        """
        yield ThinkingEvent(**THINKING_MESSAGES["analyzing"])

        trace = create_trace("agent_turn", metadata={"user_message": message})
        state = LoopState(history=history + [{"role": "user", "content": message}])

        while state.iteration < self._max_iterations:
            # --- Planner ---
            planner_span = create_span(trace, "planner", input={"iteration": state.iteration})
            meta = llm_metadata(planner_span, "planner")

            plan = self._planner.plan(
                history=state.history,
                previous_results=state.last_results or None,
                evaluator_feedback=state.evaluator_feedback,
                metadata=meta,
            )
            state.last_plan = plan

            end_span(planner_span, output={
                "action": plan.action,
                "reasoning_trace": plan.reasoning_trace,
            })

            if plan.action == "clarify":
                yield ClarifyEvent()
                conv_span = create_span(trace, "conversationist", input={"mode": "clarify"})
                conv_meta = llm_metadata(conv_span, "conversationist-clarify")
                for token in self._conversationist.clarify(plan.question, state.history, stream=True, metadata=conv_meta):  # type: ignore[misc]
                    yield ResponseChunkEvent(text=token)
                end_span(conv_span, output={"mode": "clarify"})
                flush_observability()
                yield DoneEvent()
                return

            if plan.action == "respond":
                yield ThinkingEvent(**THINKING_MESSAGES["responding"])
                conv_span = create_span(trace, "conversationist", input={
                    "mode": "synthesize",
                    "strategy": plan.response_strategy,
                    "product_count": len(state.last_results),
                })
                conv_meta = llm_metadata(conv_span, "conversationist-synthesize")
                for token in self._conversationist.synthesize(plan.response_strategy, state.history, state.last_results, stream=True, metadata=conv_meta):  # type: ignore[misc]
                    yield ResponseChunkEvent(text=token)
                end_span(conv_span, output={"strategy": plan.response_strategy})
                flush_observability()
                yield DoneEvent()
                return

            # action == "search"
            sp = plan.search_plan

            yield IntentEvent(
                summary=plan.intent_summary,
                semantic_query=sp.semantic_query,
                filters=_filters_dict(sp.filters),
            )

            # --- Hybrid Search ---
            search_span = create_span(trace, "hybrid_search", input={
                "semantic_query": sp.semantic_query,
                "filters": _format_filters(sp.filters),
            })

            result = self._search.search(sp)

            end_span(search_span, output={
                "candidate_count": result.candidate_count,
                "result_count": len(result.products),
            })

            # --- Evaluator ---
            eval_span = create_span(trace, "evaluator", input={
                "intent_summary": plan.intent_summary,
                "candidate_count": result.candidate_count,
            })
            eval_meta = llm_metadata(eval_span, "evaluator")

            evaluation = self._evaluator.evaluate(
                intent_summary=plan.intent_summary,
                constraints=result.applied_filters,
                products=result.products,
                candidate_count=result.candidate_count,
                metadata=eval_meta,
            )

            end_span(eval_span, output={
                "diagnosis": evaluation.diagnosis,
                "blocking_constraints": evaluation.blocking_constraints,
                "reason": evaluation.reason,
            })

            yield ThinkingEvent(
                message=THINKING_MESSAGES["evaluating"]["message"],
                detail=f"{result.candidate_count} candidates found",
            )

            # --- Curator ---
            if result.products:
                yield ThinkingEvent(**THINKING_MESSAGES["curating"])
                curator_span = create_span(trace, "curator", input={"product_count": len(result.products)})
                curator_meta = llm_metadata(curator_span, "curator")
                curator_output = self._curator.curate(
                    products=result.products,
                    intent_summary=plan.intent_summary,
                    history=state.history,
                    metadata=curator_meta,
                )
                end_span(curator_span, output={"picks": len(curator_output.picks)})
                yield ProductsEvent(
                    intro=curator_output.intro,
                    items=[p.model_dump() for p in curator_output.picks],
                )

            state.last_results = result.products
            state.evaluator_feedback = _format_feedback(evaluation, sp, result.candidate_count)
            state.iteration += 1

        # Iteration cap reached — respond with whatever we have
        strategy = strategy_for_result_count(len(state.last_results))
        yield ThinkingEvent(**THINKING_MESSAGES["responding"])
        conv_span = create_span(trace, "conversationist", input={
            "mode": "synthesize",
            "strategy": strategy,
            "product_count": len(state.last_results),
        })
        conv_meta = llm_metadata(conv_span, "conversationist-synthesize")
        for token in self._conversationist.synthesize(strategy, state.history, state.last_results, stream=True, metadata=conv_meta):  # type: ignore[misc]
            yield ResponseChunkEvent(text=token)
        end_span(conv_span, output={"strategy": strategy})
        flush_observability()
        yield DoneEvent()
