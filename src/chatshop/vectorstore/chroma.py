import chromadb

from chatshop.config import settings
from chatshop.data.models import Product

_METADATA_KEYS = frozenset({
    "title", "description", "price",
    "brand", "type", "wireless", "anc",
    "battery_hours", "waterproof_rating", "driver_size_mm", "use_cases",
})


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
            battery = meta.get("battery_hours")
            driver = meta.get("driver_size_mm")
            use_cases_raw = meta.get("use_cases", "")
            products.append(
                Product(
                    product_id=product_id,
                    title=meta.get("title", ""),
                    description=meta.get("description", ""),
                    price=price if price and price > 0 else None,
                    brand=meta.get("brand", ""),
                    type=meta.get("type", ""),
                    wireless=meta.get("wireless"),
                    anc=meta.get("anc"),
                    battery_hours=battery if battery and battery > 0 else None,
                    waterproof_rating=meta.get("waterproof_rating") or None,
                    driver_size_mm=driver if driver and driver > 0 else None,
                    use_cases=[v.strip() for v in use_cases_raw.split(",") if v.strip()],
                )
            )
        return products
