from chatshop.config import settings
from chatshop.data.models import Product
from chatshop.embeddings.embedder import Embedder
from chatshop.vectorstore.chroma import ChromaStore


class Retriever:
    """Embeds a query and returns the top-k matching Products."""

    def __init__(
        self,
        embedder: Embedder | None = None,
        store: ChromaStore | None = None,
    ) -> None:
        self._embedder = embedder or Embedder()
        self._store = store or ChromaStore()

    def retrieve(self, query: str, top_k: int | None = None) -> list[Product]:
        vector = self._embedder.encode_one(query)
        return self._store.query(vector, top_k=top_k or settings.top_k_results)
