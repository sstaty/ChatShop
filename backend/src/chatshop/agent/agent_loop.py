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
    "analyzing":  {"message": "Decoding your request...",      "detail": "Aligning cosmic signals with your intent..."},
    "searching":  {"message": "Scanning the catalogue...",     "detail": "Drifting through starfields of infinite possibilities..."},
    "evaluating": {"message": "Checking quality...",           "detail": "Running it past the intergalactic standards council..."},
    "curating":   {"message": "Picking your best options...",  "detail": "Handpicking gems from the asteroid belt..."},
    "responding": {"message": "Crafting your answer...",       "detail": "Stitching together stardust into something useful..."},
    "clarifying": {"message": "Need a bit more info...",       "detail": "My telescope needs a clearer signal..."},
}


def _card_type(product: Product) -> str:
    """Map backend product types to the frontend card image variants."""
    if product.type in {"over-ear", "in-ear", "on-ear"}:
        return product.type
    if product.type == "open-back":
        return "over-ear"
    return ""


def _product_card_item(picked_product: object, products_by_id: dict[str, Product]) -> dict:
    """Enrich a curator pick for the frontend cards.

    The frontend still reads the title from ``product_id`` for now, so the SSE
    payload intentionally swaps the raw ID for the human-readable product title.
    """
    item = picked_product.model_dump()
    product = products_by_id.get(item["product_id"])

    if product is None:
        return item

    item["product_id"] = product.title
    if product.price is not None:
        item["price"] = product.price
    product_type = _card_type(product)
    if product_type:
        item["type"] = product_type
    return item


def _filters_dict(filters: SearchFilters) -> dict:
    """Convert SearchFilters to a plain dict for IntentEvent."""
    d: dict = {}
    if filters.max_price is not None:
        d["max_price"] = filters.max_price
    if filters.min_price is not None:
        d["min_price"] = filters.min_price
    d.update(filters.extra_filters)
    return d


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


def _hydrate_shown_products(items: list[dict]) -> list[Product]:
    """Reconstruct minimal Product objects from frontend ProductItem dicts.

    The frontend stores product_id as the product title (swapped in
    _product_card_item), so we use it for both product_id and title.
    Price and type are preserved where available.
    """
    return [
        Product(
            product_id=d["product_id"],
            title=d["product_id"],
            price=d.get("price"),
            type=d.get("type", ""),
        )
        for d in items
        if d.get("product_id")
    ]


# ---------------------------------------------------------------------------
# Loop state
# ---------------------------------------------------------------------------


@dataclass
class LoopState:
    """Mutable state carried across iterations of the agent loop."""

    iteration: int = 0
    history: list[dict] = field(default_factory=list)
    last_results: list[Product] = field(default_factory=list)
    curated_products: list[Product] = field(default_factory=list)
    evaluator_feedback: str | None = None
    last_plan: "PlannerOutput | None" = None
    first_plan: "PlannerOutput | None" = None
    last_eval: "EvaluatorOutput | None" = None


# ---------------------------------------------------------------------------
# AgentResult
# ---------------------------------------------------------------------------


@dataclass
class AgentResult:
    """Structured output from a single agent turn, used by the eval system."""

    planner_output: "PlannerOutput"
    search_results: list[Product] | None
    evaluator_output: "EvaluatorOutput | None"
    final_response: str
    iterations: int
    trace_id: str | None = None


# ---------------------------------------------------------------------------
# AgentLoop
# ---------------------------------------------------------------------------


class AgentLoop:
    """Runs the plan → search → evaluate cycle for a single conversation turn.

    ``stream_with_trace`` is the canonical entry point. ``run_with_result``
    is a thin wrapper for the eval system. ``run`` and ``stream`` are
    convenience wrappers that strip trace events.
    """

    def __init__(
        self,
        planner: "Planner",
        evaluator: "Evaluator",
        hybrid_search: "HybridSearch",
        llm_client: "LLMClient",
        curator: "Curator",
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

    def stream(self, message: str, history: list[dict]) -> Iterator[str]:
        """Run the agent loop and yield the final response token by token."""
        for event in self.stream_with_trace(message, history):
            if isinstance(event, ResponseChunkEvent):
                yield event.text

    def stream_with_trace(
        self,
        message: str,
        history: list[dict],
        shown_products: list[dict] | None = None,
    ) -> Iterator[SSEEvent]:
        """Run the agent loop yielding typed SSEEvent instances.

        Args:
            message: The current user message.
            history: Prior conversation turns in OpenAI message format.
            shown_products: Product cards visible to the user from the
                previous turn. Pre-populates curated_products so follow-up
                questions have catalog context without a new search.
        """
        trace = create_trace("agent_turn", metadata={"user_message": message})
        state = LoopState(
            history=history + [{"role": "user", "content": message}],
            curated_products=_hydrate_shown_products(shown_products) if shown_products else [],
        )
        yield from self._run(state, trace)

    def run_with_result(
        self,
        message: str,
        history: list[dict],
        shown_products: list[dict] | None = None,
        *,
        parent_trace: object | None = None,
    ) -> AgentResult:
        """Run the full agent loop and return a structured :class:`AgentResult`.

        Thin wrapper over :meth:`_run` — collects response tokens and reads
        final state after the generator completes.
        """
        if parent_trace is not None:
            trace = create_span(parent_trace, "agent_turn_eval", input={"user_message": message})
        else:
            trace = create_trace("agent_turn_eval", metadata={"user_message": message})
        trace_id: str | None = getattr(trace, "id", None)

        state = LoopState(
            history=history + [{"role": "user", "content": message}],
            curated_products=_hydrate_shown_products(shown_products) if shown_products else [],
        )
        tokens: list[str] = []
        for event in self._run(state, trace):
            if isinstance(event, ResponseChunkEvent):
                tokens.append(event.text)

        if parent_trace is not None:
            end_span(trace, output={"action": getattr(state.last_plan, "action", "unknown")})

        return AgentResult(
            planner_output=state.first_plan,
            search_results=state.last_results or None,
            evaluator_output=state.last_eval,
            final_response="".join(tokens),
            iterations=state.iteration,
            trace_id=trace_id,
        )

    # ------------------------------------------------------------------
    # Core loop
    # ------------------------------------------------------------------

    def _run(self, state: LoopState, trace: object) -> Iterator[SSEEvent]:
        """Single shared loop used by both stream_with_trace and run_with_result."""
        yield ThinkingEvent(**THINKING_MESSAGES["analyzing"])

        while state.iteration < self._max_iterations:
            plan = self._call_planner(state, trace)

            if plan.action == "clarify":
                yield from self._clarify(plan, state, trace)
                return

            if plan.action == "respond":
                yield from self._respond(plan.response_strategy, state, trace)
                return

            yield from self._search_and_curate(plan, state, trace)

        # Iteration cap — respond with whatever we have
        strategy = strategy_for_result_count(len(state.last_results))
        yield from self._respond(strategy, state, trace)

    # ------------------------------------------------------------------
    # Private step methods
    # ------------------------------------------------------------------

    def _call_planner(self, state: LoopState, trace: object) -> "PlannerOutput":
        span = create_span(trace, "planner", input={"iteration": state.iteration})
        plan = self._planner.plan(
            history=state.history,
            previous_results=state.last_results or None,
            evaluator_feedback=state.evaluator_feedback,
            shown_products=state.curated_products or None,
            metadata=llm_metadata(span, "planner"),
        )
        end_span(span, output={"action": plan.action, "reasoning_trace": plan.reasoning_trace})
        state.last_plan = plan
        if state.first_plan is None:
            state.first_plan = plan
        return plan

    def _clarify(
        self, plan: "PlannerOutput", state: LoopState, trace: object
    ) -> Iterator[SSEEvent]:
        yield ClarifyEvent()
        span = create_span(trace, "conversationist", input={"mode": "clarify"})
        for token in self._conversationist.clarify(  # type: ignore[misc]
            plan.question, state.history, stream=True,
            metadata=llm_metadata(span, "conversationist-clarify"),
        ):
            yield ResponseChunkEvent(text=token)
        end_span(span, output={"mode": "clarify"})
        flush_observability()
        yield DoneEvent()

    def _respond(
        self, strategy: str, state: LoopState, trace: object
    ) -> Iterator[SSEEvent]:
        yield ThinkingEvent(**THINKING_MESSAGES["responding"])
        products = state.curated_products or state.last_results
        span = create_span(trace, "conversationist", input={
            "mode": "synthesize", "strategy": strategy, "product_count": len(products),
        })
        for token in self._conversationist.synthesize(  # type: ignore[misc]
            strategy, state.history, products, stream=True,
            metadata=llm_metadata(span, "conversationist-synthesize"),
        ):
            yield ResponseChunkEvent(text=token)
        end_span(span, output={"strategy": strategy})
        flush_observability()
        yield DoneEvent()

    def _search_and_curate(
        self, plan: "PlannerOutput", state: LoopState, trace: object
    ) -> Iterator[SSEEvent]:
        sp = plan.search_plan
        yield IntentEvent(
            summary=plan.intent_summary,
            semantic_query=sp.semantic_query,
            filters=_filters_dict(sp.filters),
        )

        # Search
        search_span = create_span(trace, "hybrid_search", input={
            "semantic_query": sp.semantic_query,
            "filters": _format_filters(sp.filters),
        })
        result = self._search.search(sp)
        end_span(search_span, output={
            "candidate_count": result.candidate_count,
            "result_count": len(result.products),
        })

        # Evaluate
        eval_span = create_span(trace, "evaluator", input={
            "intent_summary": plan.intent_summary,
            "candidate_count": result.candidate_count,
        })
        evaluation = self._evaluator.evaluate(
            intent_summary=plan.intent_summary,
            constraints=result.applied_filters,
            products=result.products,
            candidate_count=result.candidate_count,
            metadata=llm_metadata(eval_span, "evaluator"),
        )
        end_span(eval_span, output={
            "diagnosis": evaluation.diagnosis,
            "blocking_constraints": evaluation.blocking_constraints,
            "reason": evaluation.reason,
        })
        state.last_eval = evaluation

        yield ThinkingEvent(
            message=THINKING_MESSAGES["evaluating"]["message"],
            detail=f"{result.candidate_count} candidates found",
        )

        # Curator
        if result.products:
            yield ThinkingEvent(**THINKING_MESSAGES["curating"])
            curator_span = create_span(trace, "curator", input={"product_count": len(result.products)})
            curator_output = self._curator.curate(
                products=result.products,
                intent_summary=plan.intent_summary,
                history=state.history,
                metadata=llm_metadata(curator_span, "curator"),
            )
            end_span(curator_span, output={"picks": len(curator_output.picks)})
            products_by_id = {p.product_id: p for p in result.products}
            state.curated_products = [
                products_by_id[p.product_id]
                for p in curator_output.picks
                if p.product_id in products_by_id
            ]
            yield ProductsEvent(
                intro=curator_output.intro,
                items=[_product_card_item(p, products_by_id) for p in curator_output.picks],
            )

        state.last_results = result.products
        state.evaluator_feedback = _format_feedback(evaluation, sp, result.candidate_count)
        state.iteration += 1
