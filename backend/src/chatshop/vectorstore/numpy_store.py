"""Lightweight numpy-based vector store.

Loads a pre-built index (products + embeddings) from a JSON file and serves
cosine-similarity queries in memory. Designed for serverless deployments where
ChromaDB's native binaries are unavailable.

Supports the same ``where`` filter dialect as ChromaDB so that
:mod:`chatshop.rag.hybrid_search` requires no changes.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np

from chatshop.config import settings
from chatshop.data.models import Product


class NumpyStore:
    """In-memory vector store backed by a JSON index file."""

    def __init__(self, index_path: str | Path | None = None) -> None:
        path = Path(index_path or settings.vector_index_path)
        with open(path, encoding="utf-8") as f:
            data = json.load(f)

        self._products: list[Product] = [Product(**p) for p in data["products"]]
        self._vectors = np.array(data["vectors"], dtype=np.float32)  # (N, D)

    # ── Write ────────────────────────────────────────────────────────────────

    def upsert(self, products: list[Product], vectors: list[list[float]]) -> None:
        """Merge products+vectors into the in-memory store (keyed by product_id)."""
        existing = {p.product_id: i for i, p in enumerate(self._products)}
        new_products = list(self._products)
        new_vectors = list(self._vectors)

        for product, vector in zip(products, vectors):
            if product.product_id in existing:
                idx = existing[product.product_id]
                new_products[idx] = product
                new_vectors[idx] = vector
            else:
                new_products.append(product)
                new_vectors.append(vector)

        self._products = new_products
        self._vectors = np.array(new_vectors, dtype=np.float32)

    def save(self, index_path: str | Path | None = None) -> None:
        """Persist the current store to disk as JSON."""
        path = Path(index_path or settings.vector_index_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "products": [p.model_dump() for p in self._products],
                    "vectors": self._vectors.tolist(),
                },
                f,
            )

    @classmethod
    def build_empty(cls) -> "NumpyStore":
        """Return an empty store without loading from disk."""
        store = object.__new__(cls)
        store._products = []
        store._vectors = np.empty((0, 0), dtype=np.float32)
        return store

    # ── Read ─────────────────────────────────────────────────────────────────

    def query(
        self,
        vector: list[float],
        top_k: int | None = None,
        where: dict | None = None,
    ) -> list[Product]:
        k = top_k or settings.top_k_results

        # Apply metadata filters
        if where:
            mask = np.array([_matches(p, where) for p in self._products])
            products = [p for p, m in zip(self._products, mask) if m]
            vectors = self._vectors[mask]
        else:
            products = self._products
            vectors = self._vectors

        if not products:
            return []

        q = np.array(vector, dtype=np.float32)
        q /= np.linalg.norm(q) + 1e-10

        norms = np.linalg.norm(vectors, axis=1, keepdims=True) + 1e-10
        scores = (vectors / norms) @ q  # cosine similarity

        top_indices = np.argsort(scores)[::-1][: min(k, len(products))]
        return [products[i] for i in top_indices]

    def count(self) -> int:
        return len(self._products)


# ── Filter evaluation ────────────────────────────────────────────────────────

def _matches(product: Product, where: dict) -> bool:
    """Evaluate a ChromaDB-style ``where`` filter against a Product."""
    if "$and" in where:
        return all(_matches(product, clause) for clause in where["$and"])
    if "$or" in where:
        return any(_matches(product, clause) for clause in where["$or"])

    # Single field condition: {"field": {"$op": value}}
    for field, condition in where.items():
        value = _get_field(product, field)
        if not _eval_condition(value, condition):
            return False
    return True


def _get_field(product: Product, field: str) -> Any:
    return getattr(product, field, None)


def _eval_condition(value: Any, condition: Any) -> bool:
    if not isinstance(condition, dict):
        return value == condition
    for op, operand in condition.items():
        if op == "$eq" and value != operand:
            return False
        if op == "$ne" and value == operand:
            return False
        if op == "$gt" and not (value is not None and value > operand):
            return False
        if op == "$gte" and not (value is not None and value >= operand):
            return False
        if op == "$lt" and not (value is not None and value < operand):
            return False
        if op == "$lte" and not (value is not None and value <= operand):
            return False
    return True
