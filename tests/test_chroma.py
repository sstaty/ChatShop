"""Integration tests for ChromaStore using a temporary directory."""

import tempfile

import pytest

from chatshop.data.models import Product
from chatshop.vectorstore.chroma import ChromaStore


def _make_product(product_id: str, title: str) -> Product:
    return Product(
        product_id=product_id,
        title=title,
        description=f"Description for {title}",
        price=99.99,
        rating=4.5,
        rating_count=100,
    )


def _zero_vector(dim: int = 384) -> list[float]:
    v = [0.0] * dim
    v[0] = 1.0  # non-zero so it's valid
    return v


@pytest.fixture
def store(tmp_path):
    return ChromaStore(persist_dir=str(tmp_path), collection_name="test_products")


def test_upsert_and_count(store):
    products = [_make_product(f"B00{i}", f"Product {i}") for i in range(5)]
    vectors = [_zero_vector() for _ in products]
    store.upsert(products, vectors)
    assert store.count() == 5


def test_upsert_empty_is_safe(store):
    store.upsert([], [])
    assert store.count() == 0


def test_query_returns_products(store):
    products = [_make_product(f"B00{i}", f"Laptop {i}") for i in range(3)]
    vectors = [_zero_vector() for _ in products]
    store.upsert(products, vectors)

    results = store.query(_zero_vector(), top_k=3)
    assert len(results) == 3
    assert all(isinstance(p, Product) for p in results)


def test_query_product_fields(store):
    product = _make_product("BABC123", "Noise Cancelling Headphones")
    store.upsert([product], [_zero_vector()])

    results = store.query(_zero_vector(), top_k=1)
    assert len(results) == 1
    result = results[0]
    assert result.product_id == "BABC123"
    assert result.title == "Noise Cancelling Headphones"
    assert result.price == pytest.approx(99.99)
    assert result.rating == pytest.approx(4.5)


def test_upsert_is_idempotent(store):
    product = _make_product("BDUP01", "Duplicate Product")
    vector = _zero_vector()
    store.upsert([product], [vector])
    store.upsert([product], [vector])
    assert store.count() == 1
