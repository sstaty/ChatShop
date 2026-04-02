"""Unit tests for AgentLoop — minimal mocking, focused on loop control logic."""

from unittest.mock import MagicMock

from chatshop.agent.agent_loop import AgentLoop, LoopState
from chatshop.agent.curator import PickedProduct, ProductSelectionOutput
from chatshop.agent.evaluator import EvaluatorOutput
from chatshop.api.sse_events import ProductsEvent, ResponseChunkEvent
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
        Product(product_id="B001", title="Sony WH-1000XM5", price=349.99, type="over-ear"),
        Product(product_id="B002", title="Anker Q35", price=79.00, type="in-ear"),
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


def _sufficient_eval() -> EvaluatorOutput:
    return EvaluatorOutput(
        diagnosis="sufficient",
        blocking_constraints=[],
        reason="Results look good.",
    )


def _unsatisfied_eval(diagnosis: str = "no_results") -> EvaluatorOutput:
    return EvaluatorOutput(
        diagnosis=diagnosis,
        blocking_constraints=["price"],
        reason="Too restrictive.",
    )


def _sample_curator_output() -> ProductSelectionOutput:
    return ProductSelectionOutput(
        intro="Found 2 great options.",
        picks=[
            PickedProduct(
                product_id="B001",
                badge="best match",
                rationale="Great ANC for commuting.",
                key_attrs=["wireless", "ANC", "30h battery"],
            ),
            PickedProduct(
                product_id="B002",
                badge="best value",
                rationale="Solid option at a lower price.",
                key_attrs=["wireless", "under $100"],
            ),
        ],
    )


def _make_loop(planner_actions: list, products: list[Product] | None = None) -> AgentLoop:
    """Build an AgentLoop with mocked dependencies."""
    planner = MagicMock()
    planner.plan.side_effect = planner_actions

    evaluator = MagicMock()
    evaluator.evaluate.return_value = _sufficient_eval()

    search = MagicMock()
    resolved = _sample_products() if products is None else products
    search.search.return_value = SearchResult(
        products=resolved,
        candidate_count=len(resolved),
        applied_filters={},
    )

    llm = MagicMock()
    llm.complete.return_value = "Here are my recommendations."
    llm.stream.return_value = iter(["Here ", "are ", "my ", "recommendations."])

    curator = MagicMock()
    curator.curate.return_value = _sample_curator_output()

    return AgentLoop(
        planner=planner,
        evaluator=evaluator,
        hybrid_search=search,
        llm_client=llm,
        curator=curator,
        max_iterations=3,
    )


# ── LoopState defaults ────────────────────────────────────────────────────────


def test_loop_state_defaults():
    state = LoopState()
    assert state.iteration == 0
    assert state.history == []
    assert state.last_results == []
    assert state.curated_products == []
    assert state.evaluator_feedback is None
    assert state.last_plan is None
    assert state.first_plan is None
    assert state.last_eval is None


# ── run() — clarify ───────────────────────────────────────────────────────────


def test_clarify_triggers_search_skip():
    """A clarify action must not trigger a search call."""
    clarify = ClarifyAction(action="clarify", question="What is your budget?", reasoning_trace="")
    loop = _make_loop([clarify])
    loop.run("headphones", history=[])
    loop._search.search.assert_not_called()


# ── run() — immediate respond ─────────────────────────────────────────────────


def test_respond_immediately_skips_search():
    loop = _make_loop([_respond_action()])
    loop.run("best headphones under $100", history=[])
    loop._search.search.assert_not_called()


# ── run() — search then respond ───────────────────────────────────────────────


def test_single_search_then_respond():
    loop = _make_loop([_search_action(), _respond_action()])
    result = loop.run("wireless headphones", history=[])
    assert isinstance(result, str)
    loop._search.search.assert_called_once()
    loop._evaluator.evaluate.assert_called_once()


# ── Planner.plan() — deterministic early-return (unit tests, no loop) ─────────


def _make_planner() -> "Planner":
    from chatshop.agent.planner import Planner
    return Planner(llm_client=MagicMock(), query_rewriter=MagicMock())


def test_planner_early_return_sufficient():
    """3+ results → Planner returns catalog_with_recommendation without calling LLM."""
    three_products = _sample_products() + [Product(product_id="B003", title="AKG K240", price=79.0)]
    planner = _make_planner()
    result = planner.plan(
        history=[{"role": "user", "content": "headphones"}],
        previous_results=three_products,
    )
    assert result.action == "respond"
    assert result.response_strategy == "catalog_with_recommendation"
    planner._llm.complete.assert_not_called()


def test_planner_early_return_narrow():
    """1–2 results → Planner returns narrow_results without calling LLM."""
    planner = _make_planner()
    result = planner.plan(
        history=[{"role": "user", "content": "headphones"}],
        previous_results=_sample_products(),  # 2 products
    )
    assert result.action == "respond"
    assert result.response_strategy == "narrow_results"
    planner._llm.complete.assert_not_called()


# ── run() — zero results → Planner clarifies ──────────────────────────────────


def test_zero_results_planner_clarifies():
    """0 results → Evaluator called, Planner called twice (search then clarify)."""
    clarify = ClarifyAction(action="clarify", question="No results — adjust budget?", reasoning_trace="")
    loop = _make_loop([_search_action(), clarify], products=[])
    loop._evaluator.evaluate.return_value = _unsatisfied_eval("no_results")
    loop.run("wireless headphones", history=[])
    assert loop._planner.plan.call_count == 2
    assert loop._search.search.call_count == 1
    assert loop._evaluator.evaluate.call_count == 1


# ── run() — iteration cap ─────────────────────────────────────────────────────


def test_iteration_cap_stops_loop():
    """Loop must stop after max_iterations even if planner keeps returning search."""
    planner = MagicMock()
    planner.plan.return_value = _search_action()  # always search

    evaluator = MagicMock()
    evaluator.evaluate.return_value = _unsatisfied_eval("no_results")

    search = MagicMock()
    search.search.return_value = SearchResult(
        products=_sample_products(), candidate_count=5, applied_filters={}
    )

    llm = MagicMock()
    llm.complete.return_value = "Forced response."
    llm.stream.return_value = iter(["Forced response."])

    curator = MagicMock()
    curator.curate.return_value = _sample_curator_output()

    loop = AgentLoop(
        planner=planner,
        evaluator=evaluator,
        hybrid_search=search,
        llm_client=llm,
        curator=curator,
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
    evaluator.evaluate.return_value = _unsatisfied_eval("no_results")

    search = MagicMock()
    search.search.return_value = SearchResult(products=[], candidate_count=0, applied_filters={})

    llm = MagicMock()
    llm.complete.return_value = "No products found."
    llm.stream.return_value = iter(["No products found."])

    curator = MagicMock()
    curator.curate.return_value = ProductSelectionOutput(intro="No good options.", picks=[])

    loop = AgentLoop(
        planner=planner, evaluator=evaluator, hybrid_search=search, llm_client=llm,
        curator=curator, max_iterations=1,
    )
    loop.run("headphones", history=[])

    # Verify synthesis was called (stream used for final response)
    llm.stream.assert_called_once()
    # The no_results strategy instruction mentions "survived" — check it's in the system message
    call_messages = llm.stream.call_args[0][0]
    system_content = call_messages[0]["content"]
    assert "survived" in system_content or "catalog" in system_content


# ── run() — narrow_results fallback ───────────────────────────────────────────


def test_narrow_results_strategy_at_cap():
    """Cap hit with 1–2 products → synthesis uses 'narrow_results' strategy."""
    planner = MagicMock()
    planner.plan.return_value = _search_action()

    evaluator = MagicMock()
    evaluator.evaluate.return_value = _unsatisfied_eval("narrow_results")

    search = MagicMock()
    search.search.return_value = SearchResult(
        products=_sample_products(), candidate_count=2, applied_filters={}
    )

    llm = MagicMock()
    llm.complete.return_value = "Limited options."
    llm.stream.return_value = iter(["Limited options."])

    curator = MagicMock()
    curator.curate.return_value = _sample_curator_output()

    loop = AgentLoop(
        planner=planner, evaluator=evaluator, hybrid_search=search, llm_client=llm,
        curator=curator, max_iterations=1,
    )
    loop.run("headphones", history=[])

    llm.stream.assert_called_once()
    call_messages = llm.stream.call_args[0][0]
    system_content = call_messages[0]["content"]
    # The narrow_results strategy instruction mentions "1–2 products"
    assert "1–2 products" in system_content


# ── stream() ─────────────────────────────────────────────────────────────────


def test_stream_yields_tokens():
    loop = _make_loop([_search_action(), _respond_action()])
    tokens = list(loop.stream("wireless headphones", history=[]))
    assert "".join(tokens) == "Here are my recommendations."


def test_stream_clarify_yields_question():
    clarify = ClarifyAction(action="clarify", question="What is your use case?", reasoning_trace="")
    loop = _make_loop([clarify])
    tokens = list(loop.stream("headphones", history=[]))
    assert "".join(tokens) == "Here are my recommendations."
    # Verify the raw question was passed through to the LLM
    call_messages = loop._conversationist._llm.stream.call_args[0][0]
    last_msg = call_messages[-1]["content"]
    assert "What is your use case?" in last_msg


# ── Curator integration ───────────────────────────────────────────────────────


def test_curator_called_after_search_with_products():
    """Curator must be called once after search returns products."""
    loop = _make_loop([_search_action(), _respond_action()])
    loop.run("wireless headphones", history=[])
    loop._curator.curate.assert_called_once()


def test_curator_not_called_when_no_products():
    """Curator must be skipped when search returns no products."""
    loop = _make_loop([_search_action(), _respond_action()], products=[])
    loop.run("wireless headphones", history=[])
    loop._curator.curate.assert_not_called()


def test_synthesize_receives_curated_products():
    """synthesize must be called with curated picks, not all search results."""
    # Search returns 2 products but curator only picks the first one
    all_products = _sample_products()  # 2 products
    curator_output = ProductSelectionOutput(
        intro="Found 1 top pick.",
        picks=[
            PickedProduct(
                product_id="B001",
                badge="best match",
                rationale="Perfect for commuting.",
                key_attrs=["wireless", "ANC"],
            )
        ],
    )

    loop = _make_loop([_search_action(), _respond_action()])
    loop._curator.curate.return_value = curator_output

    list(loop.stream_with_trace("wireless headphones", history=[]))

    call_messages = loop._conversationist._llm.stream.call_args[0][0]
    last_msg = call_messages[-1]["content"]
    # Only the curated product should appear in the catalog
    assert "Sony WH-1000XM5" in last_msg
    assert "Anker Q35" not in last_msg


def test_stream_emits_products_event_after_search():
    """stream_with_trace must emit a ProductsEvent after curator runs."""
    loop = _make_loop([_search_action(), _respond_action()])
    events = list(loop.stream_with_trace("wireless headphones", history=[]))
    products_events = [e for e in events if isinstance(e, ProductsEvent)]
    assert len(products_events) == 1
    assert products_events[0].intro == "Found 2 great options."
    assert len(products_events[0].items) == 2
    assert products_events[0].items[0]["product_id"] == "Sony WH-1000XM5"
    assert products_events[0].items[0]["price"] == 349.99
    assert products_events[0].items[0]["type"] == "over-ear"
    assert products_events[0].items[1]["product_id"] == "Anker Q35"
    assert products_events[0].items[1]["price"] == 79.00
    assert products_events[0].items[1]["type"] == "in-ear"


def test_stream_no_products_event_when_empty_results():
    """stream_with_trace must not emit ProductsEvent when search finds nothing."""
    loop = _make_loop([_search_action(), _respond_action()], products=[])
    events = list(loop.stream_with_trace("wireless headphones", history=[]))
    assert not any(isinstance(e, ProductsEvent) for e in events)


def test_stream_response_chunks_contain_tokens():
    """stream_with_trace must emit ResponseChunkEvent for each LLM token."""
    loop = _make_loop([_search_action(), _respond_action()])
    events = list(loop.stream_with_trace("wireless headphones", history=[]))
    chunks = [e for e in events if isinstance(e, ResponseChunkEvent)]
    assert "".join(c.text for c in chunks) == "Here are my recommendations."
