"""
Eval fixtures — real AgentLoop with real ChromaDB and real LLM calls.
Mirrors the wiring in gradio_app._get_agent_loop().
"""

from __future__ import annotations

import pytest

from chatshop.agent.agent_loop import AgentLoop
from chatshop.agent.evaluator import Evaluator
from chatshop.agent.planner import Planner
from chatshop.config import settings
from chatshop.infra.llm_client import llm_client_for
from chatshop.infra.observability import init_observability
from chatshop.rag.hybrid_search import HybridSearch
from chatshop.rag.query_rewriter import QueryRewriter
from chatshop.rag.retriever import Retriever

from tests.evals.judge import EvalJudge
from tests.evals.report import generate_report

# Module-level accumulator — appended to by test_eval.py during the session.
_eval_results: list = []


@pytest.fixture(scope="session")
def agent_loop() -> AgentLoop:
    """Real AgentLoop with real ChromaDB and real LLM calls."""
    init_observability()
    planner_llm = llm_client_for(settings.planner_model)
    rewriter_llm = llm_client_for(settings.query_rewriter_model)
    evaluator_llm = llm_client_for(settings.evaluator_model)
    synthesis_llm = llm_client_for(settings.synthesis_model)

    return AgentLoop(
        planner=Planner(planner_llm, QueryRewriter(rewriter_llm)),
        evaluator=Evaluator(evaluator_llm),
        hybrid_search=HybridSearch(Retriever()),
        llm_client=synthesis_llm,
    )


@pytest.fixture(scope="session")
def eval_judge() -> EvalJudge:
    """LLM-as-judge client."""
    return EvalJudge(llm_client_for(settings.eval_judge_model))


@pytest.fixture(scope="session")
def eval_results() -> list:
    """Session-scoped list that accumulates (case, result, scores) tuples.

    Tests append to this list; the terminal summary hook generates the report.
    """
    return _eval_results


def pytest_terminal_summary(terminalreporter, exitstatus, config) -> None:  # type: ignore[no-untyped-def]
    """Generate the eval report after the test session ends."""
    if _eval_results:
        generate_report(_eval_results)
