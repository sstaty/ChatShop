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

from chatshop.agent.planner import SearchPlan
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
        ...

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
        ...
