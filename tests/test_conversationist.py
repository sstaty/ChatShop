"""Unit tests for Conversationist — verify message construction and strategy routing."""

from unittest.mock import MagicMock

import pytest

from chatshop.agent.conversationist import (
    Conversationist,
    _CLARIFY_INSTRUCTION,
    _STRATEGY_INSTRUCTIONS,
    _SYSTEM_PROMPT,
)
from chatshop.data.models import Product


# ── Fixtures ──────────────────────────────────────────────────────────────────


def _make_conversationist():
    llm = MagicMock()
    llm.complete.return_value = "Mock response."
    llm.stream.return_value = iter(["Mock ", "response."])
    return Conversationist(llm), llm


def _sample_products():
    return [Product(product_id="B001", title="Sony WH-1000XM5", price=349.99)]


def _sample_history():
    return [{"role": "user", "content": "I want headphones"}]


# ── synthesize — strategy instructions ────────────────────────────────────────


@pytest.mark.parametrize("strategy", list(_STRATEGY_INSTRUCTIONS.keys()))
def test_synthesize_includes_strategy_instruction(strategy):
    """Each strategy key injects its instruction into the system prompt."""
    conv, llm = _make_conversationist()
    conv.synthesize(strategy, _sample_history(), _sample_products())

    call_messages = llm.complete.call_args[0][0]
    system_content = call_messages[0]["content"]
    assert _SYSTEM_PROMPT in system_content
    assert _STRATEGY_INSTRUCTIONS[strategy] in system_content


def test_synthesize_unknown_strategy_falls_back():
    """Unknown strategy key silently uses catalog_with_recommendation."""
    conv, llm = _make_conversationist()
    conv.synthesize("nonexistent_strategy", _sample_history(), _sample_products())

    call_messages = llm.complete.call_args[0][0]
    system_content = call_messages[0]["content"]
    assert _STRATEGY_INSTRUCTIONS["catalog_with_recommendation"] in system_content


# ── synthesize — product injection ────────────────────────────────────────────


def test_synthesize_injects_products():
    """Product titles appear in the final user message."""
    conv, llm = _make_conversationist()
    conv.synthesize("catalog_with_recommendation", _sample_history(), _sample_products())

    call_messages = llm.complete.call_args[0][0]
    last_msg = call_messages[-1]["content"]
    assert "Sony WH-1000XM5" in last_msg


def test_synthesize_no_products():
    """Empty product list still produces a valid call (for informational/off_topic)."""
    conv, llm = _make_conversationist()
    conv.synthesize("informational", _sample_history(), [])
    llm.complete.assert_called_once()


# ── synthesize — history injection ────────────────────────────────────────────


def test_synthesize_injects_history():
    """Multi-turn history appears between system and final user messages."""
    history = [
        {"role": "user", "content": "Hi"},
        {"role": "assistant", "content": "Hello!"},
        {"role": "user", "content": "Show me headphones"},
    ]
    conv, llm = _make_conversationist()
    conv.synthesize("catalog_with_recommendation", history, _sample_products())

    call_messages = llm.complete.call_args[0][0]
    # System message first, then history[:-1], then final user message
    assert call_messages[0]["role"] == "system"
    assert call_messages[1]["content"] == "Hi"
    assert call_messages[2]["content"] == "Hello!"
    # Final message is the last user turn with product catalog injected
    assert call_messages[-1]["role"] == "user"
    assert "Show me headphones" in call_messages[-1]["content"]


# ── clarify ───────────────────────────────────────────────────────────────────


def test_clarify_includes_raw_question():
    """Raw question appears in the final user message."""
    conv, llm = _make_conversationist()
    conv.clarify("What is your budget?", _sample_history())

    call_messages = llm.complete.call_args[0][0]
    system_content = call_messages[0]["content"]
    assert _CLARIFY_INSTRUCTION in system_content
    last_msg = call_messages[-1]["content"]
    assert "What is your budget?" in last_msg


# ── stream modes ──────────────────────────────────────────────────────────────


def test_synthesize_stream_calls_stream():
    """stream=True uses llm.stream, not llm.complete."""
    conv, llm = _make_conversationist()
    result = conv.synthesize("catalog_with_recommendation", _sample_history(), _sample_products(), stream=True)
    # Consume the iterator
    list(result)
    llm.stream.assert_called_once()
    llm.complete.assert_not_called()


def test_clarify_stream_calls_stream():
    """stream=True uses llm.stream, not llm.complete."""
    conv, llm = _make_conversationist()
    result = conv.clarify("What is your budget?", _sample_history(), stream=True)
    list(result)
    llm.stream.assert_called_once()
    llm.complete.assert_not_called()
