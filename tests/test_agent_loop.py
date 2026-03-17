"""Unit tests for AgentLoop — minimal mocking, focused on loop control logic."""

from unittest.mock import MagicMock

from chatshop.agent.agent_loop import AgentLoop, LoopState
from chatshop.agent.evaluator import EvaluatorOutput
from chatshop.agent.planner import (
    ClarifyAction,
    RespondAction,
    SearchAction,
    SearchPlan,
    SearchFilters,
)
from chatshop.data.models import Product
from chatshop.rag.hybrid_search import SearchResult


# ── Fixtures ──────────────────────────────────────────────────────────────────


def _sample_products() -> list[Product]:
    return [
        Product(product_id="B001", title="Sony WH-1000XM5", price=349.99),
        Product(product_id="B002", title="Anker Q35", price=79.00),
    ]


def _search_action() -> SearchAction:
    return SearchAction(
        action="search",
        search_plan=SearchPlan(semantic_query="wireless headphones", filters=SearchFilters()),
        reasoning_trace="",
        intent_summary="User wants wireless headphones.",
    )


def _respond_action(strategy: str = "catalog_with_recommendation") -> RespondAction:
    return RespondAction(action="respond", response_strategy=strategy, reasoning_trace="")


def _make_loop(planner_actions: list, products: list[Product] | None = None) -> AgentLoop:
    """Build an AgentLoop with mocked dependencies."""
    planner = MagicMock()
    planner.plan.side_effect = planner_actions

    evaluator = MagicMock()
    evaluator.evaluate.return_value = EvaluatorOutput(
        satisfactory=True, reason="Results look good."
    )

    search = MagicMock()
    search.search.return_value = SearchResult(
        products=products or _sample_products(),
        candidate_count=5,
        applied_filters={},
    )

    llm = MagicMock()
    llm.complete.return_value = "Here are my recommendations."
    llm.stream.return_value = iter(["Here ", "are ", "my ", "recommendations."])

    return AgentLoop(
        planner=planner,
        evaluator=evaluator,
        hybrid_search=search,
        llm_client=llm,
        max_iterations=3,
    )


# ── LoopState defaults ────────────────────────────────────────────────────────


def test_loop_state_defaults():
    state = LoopState()
    assert state.iteration == 0
    assert state.history == []
    assert state.last_results == []
    assert state.evaluator_feedback is None
    assert state.finished is False
    assert state.last_plan is None


# ── run() — clarify ───────────────────────────────────────────────────────────


def test_clarify_returns_question():
    clarify = ClarifyAction(action="clarify", question="What is your budget?", reasoning_trace="")
    loop = _make_loop([clarify])
    result = loop.run("headphones", history=[])
    assert result == "What is your budget?"
    loop._search.search.assert_not_called()
    loop._llm.complete.assert_not_called()


# ── run() — immediate respond ─────────────────────────────────────────────────


def test_respond_immediately_skips_search():
    loop = _make_loop([_respond_action()])
    loop.run("best headphones under $100", history=[])
    loop._search.search.assert_not_called()
    loop._llm.complete.assert_called_once()


# ── run() — search then respond ───────────────────────────────────────────────


def test_single_search_then_respond():
    loop = _make_loop([_search_action(), _respond_action()])
    result = loop.run("wireless headphones", history=[])
    assert isinstance(result, str)
    loop._search.search.assert_called_once()
    loop._evaluator.evaluate.assert_called_once()


# ── run() — iteration cap ─────────────────────────────────────────────────────


def test_iteration_cap_stops_loop():
    """Loop must stop after max_iterations even if planner keeps returning search."""
    planner = MagicMock()
    planner.plan.return_value = _search_action()  # always search

    evaluator = MagicMock()
    evaluator.evaluate.return_value = EvaluatorOutput(satisfactory=False, reason="Not good.")

    search = MagicMock()
    search.search.return_value = SearchResult(
        products=_sample_products(), candidate_count=5, applied_filters={}
    )

    llm = MagicMock()
    llm.complete.return_value = "Forced response."

    loop = AgentLoop(
        planner=planner,
        evaluator=evaluator,
        hybrid_search=search,
        llm_client=llm,
        max_iterations=2,
    )
    result = loop.run("headphones", history=[])

    assert planner.plan.call_count == 2
    assert isinstance(result, str)


# ── run() — no_results fallback ───────────────────────────────────────────────


def test_no_results_strategy_when_no_products():
    """Cap hit with empty products → synthesis uses 'no_results' strategy."""
    planner = MagicMock()
    planner.plan.return_value = _search_action()

    evaluator = MagicMock()
    evaluator.evaluate.return_value = EvaluatorOutput(satisfactory=False, reason="Nothing found.")

    search = MagicMock()
    search.search.return_value = SearchResult(products=[], candidate_count=0, applied_filters={})

    llm = MagicMock()
    llm.complete.return_value = "No products found."

    loop = AgentLoop(
        planner=planner, evaluator=evaluator, hybrid_search=search, llm_client=llm, max_iterations=1
    )
    loop.run("headphones", history=[])

    call_messages = llm.complete.call_args[0][0]
    assert any("no_results" in str(m) or "No products matched" in str(m) for m in call_messages)


# ── stream() ─────────────────────────────────────────────────────────────────


def test_stream_yields_tokens():
    loop = _make_loop([_search_action(), _respond_action()])
    tokens = list(loop.stream("wireless headphones", history=[]))
    assert "".join(tokens) == "Here are my recommendations."


def test_stream_clarify_yields_question():
    clarify = ClarifyAction(action="clarify", question="What is your use case?", reasoning_trace="")
    loop = _make_loop([clarify])
    tokens = list(loop.stream("headphones", history=[]))
    assert tokens == ["What is your use case?"]
