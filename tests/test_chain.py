"""Unit tests for RAGChain with mocked litellm and retriever."""

from unittest.mock import MagicMock, patch

import pytest

from chatshop.data.models import Product
from chatshop.rag.chain import RAGChain
from chatshop.rag.prompt import SYSTEM_PROMPT, build_user_message


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _sample_products() -> list[Product]:
    return [
        Product(
            product_id="B001",
            title="Sony WH-1000XM5 Headphones",
            description="Industry-leading noise cancellation.",
            price=349.99,
            rating=4.7,
            rating_count=12000,
        ),
        Product(
            product_id="B002",
            title="Apple AirPods Pro",
            description="Active noise cancellation with transparency mode.",
            price=249.00,
            rating=4.6,
            rating_count=50000,
        ),
    ]


def _mock_retriever(products: list[Product]) -> MagicMock:
    retriever = MagicMock()
    retriever.retrieve.return_value = products
    return retriever


def _mock_completion_response(content: str) -> MagicMock:
    message = MagicMock()
    message.content = content
    choice = MagicMock()
    choice.message = message
    response = MagicMock()
    response.choices = [choice]
    return response


def _mock_stream_chunks(tokens: list[str]) -> list[MagicMock]:
    chunks = []
    for token in tokens:
        delta = MagicMock()
        delta.content = token
        choice = MagicMock()
        choice.delta = delta
        chunk = MagicMock()
        chunk.choices = [choice]
        chunks.append(chunk)
    return chunks


# ── prompt.py tests ───────────────────────────────────────────────────────────

def test_system_prompt_non_empty():
    assert len(SYSTEM_PROMPT) > 50


def test_build_user_message_contains_query():
    products = _sample_products()
    message = build_user_message("headphones under $300", products)
    assert "headphones under $300" in message


def test_build_user_message_contains_product_titles():
    products = _sample_products()
    message = build_user_message("headphones", products)
    assert "Sony WH-1000XM5" in message
    assert "AirPods Pro" in message


def test_build_user_message_contains_prices():
    products = _sample_products()
    message = build_user_message("headphones", products)
    assert "349.99" in message
    assert "249.00" in message


def test_build_user_message_numbered():
    products = _sample_products()
    message = build_user_message("headphones", products)
    assert "[1]" in message
    assert "[2]" in message


# ── chain.run() tests ─────────────────────────────────────────────────────────

def test_chain_run_returns_string():
    products = _sample_products()
    retriever = _mock_retriever(products)

    with patch("chatshop.rag.chain.litellm.completion") as mock_completion:
        mock_completion.return_value = _mock_completion_response("I recommend the Sony headphones.")
        chain = RAGChain(retriever=retriever)
        result = chain.run("best headphones")

    assert isinstance(result, str)
    assert "Sony" in result


def test_chain_run_calls_retriever_with_query():
    products = _sample_products()
    retriever = _mock_retriever(products)

    with patch("chatshop.rag.chain.litellm.completion") as mock_completion:
        mock_completion.return_value = _mock_completion_response("response")
        chain = RAGChain(retriever=retriever)
        chain.run("wireless headphones under $100")

    retriever.retrieve.assert_called_once_with("wireless headphones under $100")


def test_chain_run_sends_system_prompt():
    products = _sample_products()
    retriever = _mock_retriever(products)

    with patch("chatshop.rag.chain.litellm.completion") as mock_completion:
        mock_completion.return_value = _mock_completion_response("response")
        chain = RAGChain(retriever=retriever)
        chain.run("query")

    call_kwargs = mock_completion.call_args
    messages = call_kwargs.kwargs.get("messages") or call_kwargs.args[1] if call_kwargs.args else call_kwargs.kwargs["messages"]
    system_messages = [m for m in messages if m["role"] == "system"]
    assert len(system_messages) == 1
    assert system_messages[0]["content"] == SYSTEM_PROMPT


def test_chain_run_includes_products_in_user_message():
    products = _sample_products()
    retriever = _mock_retriever(products)

    with patch("chatshop.rag.chain.litellm.completion") as mock_completion:
        mock_completion.return_value = _mock_completion_response("response")
        chain = RAGChain(retriever=retriever)
        chain.run("headphones")

    call_kwargs = mock_completion.call_args
    messages = call_kwargs.kwargs.get("messages") or call_kwargs.kwargs["messages"]
    user_messages = [m for m in messages if m["role"] == "user"]
    assert len(user_messages) == 1
    assert "Sony WH-1000XM5" in user_messages[0]["content"]


# ── chain.stream() tests ──────────────────────────────────────────────────────

def test_chain_stream_yields_tokens():
    products = _sample_products()
    retriever = _mock_retriever(products)
    tokens = ["I ", "recommend ", "Sony."]

    with patch("chatshop.rag.chain.litellm.completion") as mock_completion:
        mock_completion.return_value = _mock_stream_chunks(tokens)
        chain = RAGChain(retriever=retriever)
        result_tokens = list(chain.stream("headphones"))

    assert result_tokens == tokens


def test_chain_stream_concatenates_to_full_response():
    products = _sample_products()
    retriever = _mock_retriever(products)
    tokens = ["The ", "best ", "choice ", "is ", "Sony."]

    with patch("chatshop.rag.chain.litellm.completion") as mock_completion:
        mock_completion.return_value = _mock_stream_chunks(tokens)
        chain = RAGChain(retriever=retriever)
        full_response = "".join(chain.stream("headphones"))

    assert full_response == "The best choice is Sony."
