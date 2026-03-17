"""
Hybrid search module — two-stage metadata + vector retrieval.

Implements the retrieval strategy described in the architecture:

    metadata filtering
          ↓
    candidate pool
          ↓
    vector similarity search
          ↓
    ranked top-N evidence set

Symbolic metadata filtering improves precision; semantic vector search
improves recall. This module wraps the existing :class:`~chatshop.rag.retriever.Retriever`
and applies structured filters from the Planner's :class:`~chatshop.agent.planner.SearchPlan`
before the vector step.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from chatshop.agent.planner import SearchFilters, SearchPlan
from chatshop.data.models import Product
from chatshop.rag.retriever import Retriever


@dataclass
class SearchResult:
    """Output of a single hybrid search call."""

    products: list[Product]
    """Top-N products ranked by vector similarity within the filtered pool."""

    candidate_count: int
    """Number of products that passed the metadata filter before vector ranking.

    Passed to the Evaluator — very small values indicate over-filtering.
    """

    applied_filters: dict = field(default_factory=dict)
    """Snapshot of the metadata filters that were actually applied.

    Useful for the Evaluator and for UI transparency (reasoning panel).
    """


def _build_where(filters: SearchFilters) -> dict | None:
    """Translate :class:`~chatshop.agent.planner.SearchFilters` into a ChromaDB ``where`` dict.

    Returns ``None`` when no filters are active (plain semantic search).
    Guards against sentinel values stored for None fields (e.g. price=-1.0).
    """
    conditions: list[dict] = []

    if filters.max_price is not None:
        conditions.append({"price": {"$gt": 0}})          # exclude sentinel -1.0
        conditions.append({"price": {"$lte": filters.max_price}})

    if filters.min_price is not None:
        conditions.append({"price": {"$gte": filters.min_price}})

    extra = filters.extra_filters

    if extra.get("wireless") is True:
        conditions.append({"wireless": {"$eq": True}})

    if extra.get("anc") is True:
        conditions.append({"anc": {"$eq": True}})

    if extra.get("type"):
        conditions.append({"type": {"$eq": extra["type"]}})

    if extra.get("min_battery_hours") is not None:
        conditions.append({"battery_hours": {"$gt": 0}})  # exclude sentinel -1
        conditions.append({"battery_hours": {"$gte": extra["min_battery_hours"]}})

    if not conditions:
        return None
    if len(conditions) == 1:
        return conditions[0]
    return {"$and": conditions}


class HybridSearch:
    """Executes a two-stage metadata-then-vector retrieval.

    Converts a :class:`~chatshop.agent.planner.SearchPlan` into a ChromaDB
    ``where`` clause, runs it against the vector store, and returns a ranked
    evidence set.
    """

    def __init__(self, retriever: Retriever) -> None:
        """
        Args:
            retriever: Existing Phase 1 retriever (Embedder + ChromaStore).
                HybridSearch augments it with structured filter translation.
        """
        self._store = retriever._store
        self._embedder = retriever._embedder

    def search(self, search_plan: SearchPlan) -> SearchResult:
        """Execute the two-stage retrieval described by ``search_plan``.

        Steps:
        1. Translate :attr:`~chatshop.agent.planner.SearchPlan.filters` into
           a ChromaDB ``where`` clause.
        2. Embed :attr:`~chatshop.agent.planner.SearchPlan.semantic_query`.
        3. Run vector similarity search within the filtered candidate pool.
        4. Optionally re-sort results according to
           :attr:`~chatshop.agent.planner.SearchPlan.sort_by`.

        Args:
            search_plan: Full retrieval specification from the Planner.

        Returns:
            :class:`SearchResult` with ranked products, candidate count, and
            the filters that were applied.
        """
        where = _build_where(search_plan.filters)
        vector = self._embedder.encode_one(search_plan.semantic_query)
        products = self._store.query(vector, where=where)

        if search_plan.sort_by == "price_asc":
            products.sort(key=lambda p: p.price if p.price is not None else float("inf"))
        elif search_plan.sort_by == "price_desc":
            products.sort(key=lambda p: p.price if p.price is not None else 0.0, reverse=True)

        return SearchResult(
            products=products,
            candidate_count=len(products),
            applied_filters=where or {},
        )
