"""
Eval report generation — console summary + markdown file.

generate_report(results) is called at the end of the test session
(via pytest_terminal_summary in conftest.py) with the accumulated
(case, result, scores) tuples.

Report files are saved to tests/evals/results/ with auto-generated names
encoding the model config and timestamp.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from chatshop.agent.planner import RespondAction, SearchAction
from chatshop.config import settings

from tests.evals.golden_dataset import EvalCase
from tests.evals.metrics import check_filters, check_strategy

if TYPE_CHECKING:
    from chatshop.agent.agent_loop import AgentResult
    from tests.evals.judge import JudgeScores

_RESULTS_DIR = Path(__file__).parent / "results"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _model_tag() -> str:
    """Short tag using the planner model name for the filename."""
    model = settings.planner_model.replace("/", "-").replace(".", "")
    return model


def _check_action_pass(case: EvalCase, result: AgentResult) -> bool:
    return result.planner_output.action == case.expected_action


def _check_filters_pass(case: EvalCase, result: AgentResult) -> tuple[bool, list[str]]:
    """Returns (all_passed, list_of_failure_messages)."""
    if not case.expected_filters or not isinstance(result.planner_output, SearchAction):
        return True, []
    actual_filters = result.planner_output.search_plan.filters
    filter_results = check_filters(case.expected_filters, actual_filters)
    failures = []
    for field_name, passed in filter_results.items():
        if field_name.startswith("warn_"):
            continue
        if not passed:
            failures.append(f"{field_name}: {passed}")
    return len(failures) == 0, failures


def _check_strategy_pass(case: EvalCase, result: AgentResult) -> bool:
    if not case.expected_response_strategy or not isinstance(result.planner_output, RespondAction):
        return True
    return check_strategy(case.expected_response_strategy, result.planner_output)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def generate_report(
    results: list[tuple[EvalCase, AgentResult, JudgeScores | None]],
) -> None:
    """Generate console summary and markdown file from accumulated eval results."""
    lines = _build_report_lines(results)
    console_output = "\n".join(lines)

    print("\n" + console_output)

    _RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    filename = f"eval_{_model_tag()}_{timestamp}.md"
    path = _RESULTS_DIR / filename
    path.write_text(console_output, encoding="utf-8")
    print(f"\nReport saved to: {path}")


def _build_report_lines(
    results: list[tuple[EvalCase, AgentResult, JudgeScores | None]],
) -> list[str]:
    lines: list[str] = []
    lines.append("=== ChatShop Eval Report ===")
    lines.append("")

    # Models
    lines.append("Models:")
    lines.append(f"  planner:      {settings.planner_model}")
    lines.append(f"  rewriter:     {settings.query_rewriter_model}")
    lines.append(f"  evaluator:    {settings.evaluator_model}")
    lines.append(f"  synthesis:    {settings.synthesis_model}")
    lines.append(f"  judge:        {settings.eval_judge_model}")
    lines.append("")

    # ------------------------------------------------------------------
    # Pre-compute all check results
    # ------------------------------------------------------------------
    action_by_cat: dict[str, list[tuple[bool, EvalCase, AgentResult]]] = defaultdict(list)
    filter_failures: list[str] = []
    filter_total = 0
    filter_passed = 0
    strategy_total = 0
    strategy_passed = 0

    for case, result, _scores in results:
        action_pass = _check_action_pass(case, result)
        action_by_cat[case.category].append((action_pass, case, result))

        if case.expected_filters and isinstance(result.planner_output, SearchAction):
            filter_total += 1
            ok, failures = _check_filters_pass(case, result)
            if ok:
                filter_passed += 1
            else:
                # Produce human-readable failure like the doc example:
                # [FAIL: search_05 — system set max_price=50 but expected None]
                detail = "; ".join(failures) if failures else "filter mismatch"
                filter_failures.append(f"  [FAIL: {case.id} — {detail}]")

        if case.expected_response_strategy and isinstance(result.planner_output, RespondAction):
            strategy_total += 1
            if _check_strategy_pass(case, result):
                strategy_passed += 1

    # ------------------------------------------------------------------
    # Action Routing
    # ------------------------------------------------------------------
    total_cases = len(results)
    overall_action_pass = sum(
        1 for ok, _, __ in sum(action_by_cat.values(), []) if ok
    )
    lines.append(f"Action Routing:    {overall_action_pass}/{total_cases} ({100*overall_action_pass/total_cases:.1f}%)")

    for cat in sorted(action_by_cat.keys()):
        entries = action_by_cat[cat]
        n_pass = sum(1 for ok, _, __ in entries if ok)
        n_total = len(entries)
        failures_for_cat = [
            f"[FAIL: {case.id} expected={case.expected_action} got={result.planner_output.action}]"
            for ok, case, result in entries
            if not ok
        ]
        # Inline failure on the category line (matching doc format)
        fail_str = "  " + "  ".join(failures_for_cat) if failures_for_cat else ""
        lines.append(f"  {cat}:{'':4}{n_pass}/{n_total}{fail_str}")

    lines.append("")

    # ------------------------------------------------------------------
    # Filter Extraction
    # ------------------------------------------------------------------
    if filter_total > 0:
        lines.append(f"Filter Extraction: {filter_passed}/{filter_total} ({100*filter_passed/filter_total:.1f}%)")
        for msg in filter_failures:
            lines.append(msg)
        lines.append("")

    # ------------------------------------------------------------------
    # Response Strategy
    # ------------------------------------------------------------------
    if strategy_total > 0:
        lines.append(f"Response Strategy: {strategy_passed}/{strategy_total} ({100*strategy_passed/strategy_total:.1f}%)")
        lines.append("")

    # ------------------------------------------------------------------
    # Judge Scores — fixed-width columns matching doc format:
    # Judge Scores (avg):        Ground  Help  Person  Constr  Overall
    #   clear_search (8):          4.5   4.2    4.4     4.3     4.4
    # ------------------------------------------------------------------
    judge_results = [(case, result, scores) for case, result, scores in results if scores is not None]
    if judge_results:
        lines.append("Judge Scores (avg):        Ground  Help  Person  Constr  Overall")

        scores_by_cat: dict[str, list[JudgeScores]] = defaultdict(list)
        for case, _, scores in judge_results:
            scores_by_cat[case.category].append(scores)

        def _fmt_score(val: float, is_na: bool) -> str:
            return " N/A" if is_na else f"{val:.1f}"

        def _avg(scores: list[JudgeScores], attr: str) -> float | None:
            """Average a dimension, excluding -1 N/A sentinels. Returns None if all N/A."""
            vals = [getattr(s, attr) for s in scores if getattr(s, attr) >= 0]
            return sum(vals) / len(vals) if vals else None

        for cat in sorted(scores_by_cat.keys()):
            cat_scores = scores_by_cat[cat]
            n = len(cat_scores)
            avg_g = _avg(cat_scores, "groundedness")
            avg_h = _avg(cat_scores, "helpfulness")
            avg_p = _avg(cat_scores, "personality")
            avg_c = _avg(cat_scores, "constraint_adherence")
            avg_o = sum(s.overall() for s in cat_scores) / n
            label = f"  {cat} ({n}):"
            lines.append(
                f"{label:<27}{_fmt_score(avg_g or 0, avg_g is None):>5}  "
                f"{avg_h:.1f}   {avg_p:.1f}    {_fmt_score(avg_c or 0, avg_c is None):>4}    {avg_o:.1f}"
            )

        # OVERALL row
        all_scores = [s for _, _, s in judge_results]
        n_all = len(all_scores)
        avg_g_all = _avg(all_scores, "groundedness")
        avg_h_all = _avg(all_scores, "helpfulness")
        avg_p_all = _avg(all_scores, "personality")
        avg_c_all = _avg(all_scores, "constraint_adherence")
        avg_o_all = sum(s.overall() for s in all_scores) / n_all
        lines.append(
            f"  {'OVERALL:':<25}{_fmt_score(avg_g_all or 0, avg_g_all is None):>5}  "
            f"{avg_h_all:.1f}   {avg_p_all:.1f}    {_fmt_score(avg_c_all or 0, avg_c_all is None):>4}    {avg_o_all:.1f}"
        )
        lines.append("")

    # ------------------------------------------------------------------
    # Per-case detail for failures and low scores
    # ------------------------------------------------------------------
    failed_cases: dict[str, tuple[EvalCase, AgentResult, JudgeScores | None]] = {}

    for case, result, scores in results:
        is_fail = (
            not _check_action_pass(case, result)
            or (case.expected_filters and isinstance(result.planner_output, SearchAction) and not _check_filters_pass(case, result)[0])
            or (case.expected_response_strategy and isinstance(result.planner_output, RespondAction) and not _check_strategy_pass(case, result))
            or (scores is not None and scores.overall() < 3.0)
        )
        if is_fail:
            failed_cases[case.id] = (case, result, scores)

    if failed_cases:
        lines.append("--- Case Details (failures / low scores) ---")
        lines.append("")

        for case_id, (case, result, scores) in failed_cases.items():
            lines.append(f"### {case_id} ({case.category})")
            lines.append(f"Query:           {case.query}")
            if case.history:
                lines.append(f"History:         {len(case.history)} prior turns")
            lines.append(f"Expected action: {case.expected_action}")
            lines.append(f"Actual action:   {result.planner_output.action}")
            if case.expected_response_strategy:
                actual_strat = getattr(result.planner_output, "response_strategy", "N/A")
                lines.append(f"Expected strat:  {case.expected_response_strategy}")
                lines.append(f"Actual strat:    {actual_strat}")
            if scores:
                lines.append(
                    f"Judge scores:    ground={scores.groundedness}  help={scores.helpfulness}"
                    f"  person={scores.personality}  constr={scores.constraint_adherence}"
                )
                lines.append(f"  Groundedness:  {scores.groundedness_reason}")
                lines.append(f"  Helpfulness:   {scores.helpfulness_reason}")
                lines.append(f"  Personality:   {scores.personality_reason}")
                lines.append(f"  Constraints:   {scores.constraint_adherence_reason}")
            lines.append(f"Response:        {result.final_response[:400]}")
            lines.append("")

    return lines
