"""
Deterministic metric checks for the eval system.

Three functions corresponding to layers 1-3 of the 5-layer eval architecture:
  check_action  — layer 1: did the Planner route correctly?
  check_filters — layer 2: did the QueryRewriter extract the right filters?
  check_strategy — layer 3: did the Planner pick the right response strategy?

Layers 1 and 3 are simple exact-match checks. Layer 2 uses tolerance rules
and detects false positives (unexpected filter inference).
"""

from __future__ import annotations

from typing import Any

from chatshop.agent.planner import RespondAction, SearchFilters


def check_action(expected: str, actual_action: str) -> bool:
    """Layer 1: exact match on Planner action.

    Args:
        expected: One of "clarify", "search", "respond".
        actual_action: The ``action`` field from the PlannerOutput.

    Returns:
        True if the actions match, False otherwise.
    """
    return actual_action == expected


def check_filters(expected: dict, actual: SearchFilters) -> dict[str, bool | str]:
    """Layer 2: per-field comparison of extracted filters against expectations.

    Comparison rules:
    - ``max_price``, ``min_price``: within max(10%, $5), whichever is larger
    - booleans (wireless, anc): exact match
    - strings (type): exact match
    - integers (min_battery_hours): within 1

    False-positive detection: if expected doesn't include a filter key but actual
    has it, a warning entry is added (key prefixed with "warn_"). These are not
    hard failures but indicate the system inferred a constraint the user didn't state.

    Args:
        expected: Dict mirroring SearchFilters structure. Keys not present are
            not checked ("don't care"). Supports "max_price", "min_price", and
            "extra_filters" sub-dict.
        actual: The SearchFilters extracted by the pipeline.

    Returns:
        Dict mapping field name → True (pass) / False (fail) / warning string.
        Keys starting with "warn_" are false-positive warnings, not hard failures.
    """
    results: dict[str, bool | str] = {}

    # --- Price fields ---
    for price_field in ("max_price", "min_price"):
        if price_field not in expected:
            # Check for false positive
            actual_val = getattr(actual, price_field)
            if actual_val is not None:
                results[f"warn_{price_field}"] = (
                    f"unexpected: system set {price_field}={actual_val} but expected None"
                )
            continue

        expected_val = expected[price_field]
        actual_val = getattr(actual, price_field)

        if expected_val is None:
            # Expected no price filter — flag if actual has one
            if actual_val is not None:
                results[f"warn_{price_field}"] = (
                    f"unexpected: system set {price_field}={actual_val} but expected None"
                )
        else:
            if actual_val is None:
                results[price_field] = False
            else:
                tolerance = max(expected_val * 0.10, 5.0)
                results[price_field] = abs(actual_val - expected_val) <= tolerance

    # --- Extra filters ---
    expected_extra: dict[str, Any] = expected.get("extra_filters", {})
    actual_extra: dict[str, Any] = actual.extra_filters

    for key, exp_val in expected_extra.items():
        act_val = actual_extra.get(key)
        if act_val is None:
            results[f"extra_filters.{key}"] = False
            continue

        if isinstance(exp_val, bool):
            results[f"extra_filters.{key}"] = act_val == exp_val
        elif isinstance(exp_val, int):
            results[f"extra_filters.{key}"] = abs(int(act_val) - exp_val) <= 1
        else:
            results[f"extra_filters.{key}"] = act_val == exp_val

    # False-positive detection for extra_filters not in expected
    for key, act_val in actual_extra.items():
        if key not in expected_extra:
            results[f"warn_extra_filters.{key}"] = (
                f"unexpected: system set {key}={act_val} but not in expected"
            )

    return results


def check_strategy(expected: str, actual: RespondAction) -> bool:
    """Layer 3: exact match on response strategy.

    Args:
        expected: The expected ``response_strategy`` string.
        actual: The RespondAction from the pipeline.

    Returns:
        True if the strategy matches, False otherwise.
    """
    return actual.response_strategy == expected
