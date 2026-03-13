import chromadb

from chatshop.config import settings
from chatshop.data.models import Product

# Keys stored in metadata that map to base Product fields (not extra_attrs)
_BASE_METADATA_KEYS = frozenset(
    {"title", "category", "price", "rating", "rating_count", "description"}
)


class ChromaStore:
    """Thin wrapper around ChromaDB: upsert products and query by vector."""

    def __init__(
        self,
        persist_dir: str | None = None,
        collection_name: str | None = None,
    ) -> None:
        self._client = chromadb.PersistentClient(
            path=persist_dir or settings.chroma_persist_dir
        )
        self._collection = self._client.get_or_create_collection(
            name=collection_name or settings.chroma_collection,
            metadata={"hnsw:space": "cosine"},
        )

    # ── Write ────────────────────────────────────────────────────────────────

    def upsert(self, products: list[Product], vectors: list[list[float]]) -> None:
        """Upsert products + their pre-computed embeddings into ChromaDB."""
        if not products:
            return
        self._collection.upsert(
            ids=[p.product_id for p in products],
            embeddings=vectors,
            documents=[p.to_document_text() for p in products],
            metadatas=[p.to_metadata() for p in products],
        )

    # ── Read ─────────────────────────────────────────────────────────────────

    def query(
        self,
        vector: list[float],
        top_k: int | None = None,
        where: dict | None = None,
    ) -> list[Product]:
        """Return the top-k most similar Products for the given query vector.

        Args:
            vector: Query embedding.
            top_k: Number of results; falls back to settings.top_k_results.
            where: Optional ChromaDB metadata filter dict, e.g.
                   {"price": {"$lte": 200}, "wireless": True}
        """
        k = top_k or settings.top_k_results
        kwargs: dict = dict(
            query_embeddings=[vector],
            n_results=k,
            include=["metadatas", "documents"],
        )
        if where:
            kwargs["where"] = where
        results = self._collection.query(**kwargs)
        return self._parse_results(results)

    def count(self) -> int:
        return self._collection.count()

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _parse_results(results: dict) -> list[Product]:
        products: list[Product] = []
        ids = results.get("ids", [[]])[0]
        metadatas = results.get("metadatas", [[]])[0]

        for product_id, meta in zip(ids, metadatas):
            price = meta.get("price")
            rating = meta.get("rating")
            extra_attrs = {k: v for k, v in meta.items() if k not in _BASE_METADATA_KEYS}
            products.append(
                Product(
                    product_id=product_id,
                    title=meta.get("title", ""),
                    description=meta.get("description", ""),
                    category=meta.get("category", ""),
                    price=price if price and price > 0 else None,
                    rating=rating if rating and rating > 0 else None,
                    rating_count=meta.get("rating_count") or None,
                    extra_attrs=extra_attrs,
                )
            )
        return products
