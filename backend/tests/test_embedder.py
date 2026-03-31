"""Integration-ish tests for embeddings.embedder — loads the real model."""

import math

import pytest

from chatshop.embeddings.embedder import Embedder


@pytest.fixture(scope="module")
def embedder():
    return Embedder()


def test_encode_returns_list_of_floats(embedder):
    result = embedder.encode(["hello world"])
    assert isinstance(result, list)
    assert isinstance(result[0], list)
    assert isinstance(result[0][0], float)


def test_encode_output_shape(embedder):
    texts = ["product one", "product two", "product three"]
    result = embedder.encode(texts)
    assert len(result) == 3
    # all-MiniLM-L6-v2 produces 384-dim vectors
    assert len(result[0]) == 384


def test_encode_one_matches_batch(embedder):
    text = "wireless headphones"
    batch_result = embedder.encode([text])[0]
    single_result = embedder.encode_one(text)
    for a, b in zip(batch_result, single_result):
        assert pytest.approx(a, abs=1e-5) == b


def test_embeddings_are_normalized(embedder):
    vectors = embedder.encode(["some product description"])
    norm = math.sqrt(sum(x ** 2 for x in vectors[0]))
    assert pytest.approx(norm, abs=1e-4) == 1.0


def test_similar_queries_are_closer_than_random(embedder):
    vectors = embedder.encode([
        "wireless headphones",
        "bluetooth headphones",
        "garden hose 50 feet",
    ])
    v0, v1, v2 = vectors

    def dot(a, b):
        return sum(x * y for x, y in zip(a, b))

    assert dot(v0, v1) > dot(v0, v2)
