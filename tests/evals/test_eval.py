"""
Parametrized eval entry point.

Run with:
  uv run pytest -m eval -v               # all 25 cases
  uv run pytest -m eval -k "search_01"  # single case
  EVAL_REFRESH=1 uv run pytest -m eval  # force cache refresh
"""

from __future__ import annotations

import pytest

from chatshop.agent.agent_loop import AgentLoop, AgentResult
from chatshop.agent.planner import RespondAction, SearchAction

from tests.evals.golden_dataset import GOLDEN_CASES, EvalCase
from tests.evals.judge import EvalJudge
from tests.evals.metrics import check_filters, check_strategy
from tests.evals.runner import run_or_cached


@pytest.mark.eval
@pytest.mark.parametrize("case", GOLDEN_CASES, ids=lambda c: c.id)
def test_eval(
    case: EvalCase,
    agent_loop: AgentLoop,
    eval_judge: EvalJudge,
    eval_results: list,
) -> None:
    result: AgentResult = run_or_cached(case, agent_loop)

    # ------------------------------------------------------------------
    # Layer 1: Action routing (hard assert)
    # ------------------------------------------------------------------
    assert result.planner_output.action == case.expected_action, (
        f"[{case.id}] Expected action={case.expected_action!r}, "
        f"got={result.planner_output.action!r}"
    )

    # ------------------------------------------------------------------
    # Layer 2: Filter extraction (hard assert, search cases only)
    # ------------------------------------------------------------------
    if case.expected_filters and isinstance(result.planner_output, SearchAction):
        actual_filters = result.planner_output.search_plan.filters
        filter_results = check_filters(case.expected_filters, actual_filters)

        for field_name, passed in filter_results.items():
            if field_name.startswith("warn_"):
                # False-positive warning — not a hard failure, surfaced in report
                continue
            assert passed, (
                f"[{case.id}] Filter mismatch on {field_name}: "
                f"result={filter_results}"
            )

    # ------------------------------------------------------------------
    # Layer 3: Response strategy (hard assert, respond cases only)
    # ------------------------------------------------------------------
    if case.expected_response_strategy and isinstance(result.planner_output, RespondAction):
        assert check_strategy(case.expected_response_strategy, result.planner_output), (
            f"[{case.id}] Expected strategy={case.expected_response_strategy!r}, "
            f"got={result.planner_output.response_strategy!r}"
        )

    # ------------------------------------------------------------------
    # Layers 4-5: Judge scores (collect, NEVER assert)
    # ------------------------------------------------------------------
    if result.final_response:
        scores = eval_judge.score(case, result)
        eval_results.append((case, result, scores))
