"""Runtime helpers for constructing shared application services."""

from __future__ import annotations

from chatshop.agent.agent_loop import AgentLoop

_agent_loop: AgentLoop | None = None


def get_agent_loop() -> AgentLoop:
    """Return the lazily constructed singleton AgentLoop."""
    global _agent_loop

    if _agent_loop is None:
        from chatshop.agent.evaluator import Evaluator
        from chatshop.agent.planner import Planner
        from chatshop.config import settings
        from chatshop.infra.llm_client import llm_client_for
        from chatshop.infra.observability import init_observability
        from chatshop.rag.hybrid_search import HybridSearch
        from chatshop.rag.query_rewriter import QueryRewriter
        from chatshop.rag.retriever import Retriever

        init_observability()

        planner_llm = llm_client_for(settings.planner_model)
        rewriter_llm = llm_client_for(settings.query_rewriter_model)
        evaluator_llm = llm_client_for(settings.evaluator_model)
        synthesis_llm = llm_client_for(settings.synthesis_model)

        _agent_loop = AgentLoop(
            planner=Planner(planner_llm, QueryRewriter(rewriter_llm)),
            evaluator=Evaluator(evaluator_llm),
            hybrid_search=HybridSearch(Retriever()),
            llm_client=synthesis_llm,
        )

    return _agent_loop