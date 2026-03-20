"""
Eval pipeline runner with JSON caching.

run_or_cached(case, agent_loop) -> AgentResult
  - On cache hit: deserialize and return (skips LLM pipeline calls)
  - On cache miss: run the full pipeline, serialize, cache
  - EVAL_REFRESH=1: force cache refresh

Cache path: tests/evals/.cache/{case_id}.json
Cache key includes a hash of the model config so cache is invalidated when
models change.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

from chatshop.agent.agent_loop import AgentLoop, AgentResult
from chatshop.agent.evaluator import EvaluatorOutput
from chatshop.agent.planner import (
    ClarifyAction,
    RespondAction,
    SearchAction,
    SearchFilters,
    SearchPlan,
)
from chatshop.config import settings
from chatshop.data.models import Product

from tests.evals.golden_dataset import EvalCase

_CACHE_DIR = Path(__file__).parent / ".cache"


# ---------------------------------------------------------------------------
# Cache key
# ---------------------------------------------------------------------------


def _model_config_hash() -> str:
    """Hash the current model config so cache invalidates on model changes."""
    key = "|".join([
        settings.planner_model,
        settings.query_rewriter_model,
        settings.evaluator_model,
        settings.synthesis_model,
    ])
    return hashlib.md5(key.encode()).hexdigest()[:8]


def _cache_path(case_id: str) -> Path:
    return _CACHE_DIR / f"{case_id}_{_model_config_hash()}.json"


# ---------------------------------------------------------------------------
# Serialization helpers
# ---------------------------------------------------------------------------


def _serialize_result(result: AgentResult) -> dict:
    plan = result.planner_output
    plan_dict: dict = {"action": plan.action, "reasoning_trace": plan.reasoning_trace}

    if plan.action == "clarify":
        plan_dict["question"] = plan.question  # type: ignore[union-attr]
    elif plan.action == "search":
        sp: SearchPlan = plan.search_plan  # type: ignore[union-attr]
        plan_dict["intent_summary"] = plan.intent_summary  # type: ignore[union-attr]
        plan_dict["search_plan"] = {
            "semantic_query": sp.semantic_query,
            "sort_by": sp.sort_by,
            "filters": {
                "max_price": sp.filters.max_price,
                "min_price": sp.filters.min_price,
                "extra_filters": sp.filters.extra_filters,
            },
        }
    elif plan.action == "respond":
        plan_dict["response_strategy"] = plan.response_strategy  # type: ignore[union-attr]

    evaluator_dict = None
    if result.evaluator_output is not None:
        ev = result.evaluator_output
        evaluator_dict = {
            "diagnosis": ev.diagnosis,
            "blocking_constraints": ev.blocking_constraints,
            "reason": ev.reason,
        }

    products_list = None
    if result.search_results is not None:
        products_list = [p.model_dump() for p in result.search_results]

    return {
        "planner_output": plan_dict,
        "search_results": products_list,
        "evaluator_output": evaluator_dict,
        "final_response": result.final_response,
        "iterations": result.iterations,
        "trace_id": result.trace_id,
    }


def _deserialize_result(data: dict) -> AgentResult:
    plan_data = data["planner_output"]
    action = plan_data["action"]

    if action == "clarify":
        plan = ClarifyAction(
            action="clarify",
            question=plan_data["question"],
            reasoning_trace=plan_data["reasoning_trace"],
        )
    elif action == "search":
        sp_data = plan_data["search_plan"]
        f_data = sp_data["filters"]
        plan = SearchAction(
            action="search",
            search_plan=SearchPlan(
                semantic_query=sp_data["semantic_query"],
                filters=SearchFilters(
                    max_price=f_data.get("max_price"),
                    min_price=f_data.get("min_price"),
                    extra_filters=f_data.get("extra_filters", {}),
                ),
                sort_by=sp_data.get("sort_by"),
            ),
            reasoning_trace=plan_data["reasoning_trace"],
            intent_summary=plan_data.get("intent_summary", ""),
        )
    else:
        plan = RespondAction(
            action="respond",
            response_strategy=plan_data["response_strategy"],
            reasoning_trace=plan_data["reasoning_trace"],
        )

    evaluator_output = None
    if data["evaluator_output"] is not None:
        ev = data["evaluator_output"]
        evaluator_output = EvaluatorOutput(
            diagnosis=ev["diagnosis"],
            blocking_constraints=ev["blocking_constraints"],
            reason=ev["reason"],
        )

    search_results = None
    if data["search_results"] is not None:
        search_results = [Product(**p) for p in data["search_results"]]

    return AgentResult(
        planner_output=plan,
        search_results=search_results,
        evaluator_output=evaluator_output,
        final_response=data["final_response"],
        iterations=data["iterations"],
        trace_id=data.get("trace_id"),
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def run_or_cached(
    case: EvalCase, agent_loop: AgentLoop, *, parent_trace: Any = None,
) -> AgentResult:
    """Run the pipeline for *case* or return a cached result.

    The cache is keyed by ``(case_id, model_config_hash)`` so it
    invalidates automatically when models change.

    Set ``EVAL_REFRESH=1`` to force a fresh pipeline run regardless of cache.

    If *parent_trace* is provided, the agent loop nests its spans under it
    so all eval cases appear in a single Langfuse trace.
    """
    path = _cache_path(case.id)
    refresh = os.environ.get("EVAL_REFRESH", "0") == "1"

    if not refresh and path.exists():
        data = json.loads(path.read_text(encoding="utf-8"))
        return _deserialize_result(data)

    result = agent_loop.run_with_result(case.query, case.history, parent_trace=parent_trace)

    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(_serialize_result(result), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return result
