from sentence_transformers import SentenceTransformer

from chatshop.config import settings


class Embedder:
    """Wraps sentence-transformers for batch encoding."""

    def __init__(self, model_name: str | None = None) -> None:
        self._model = SentenceTransformer(model_name or settings.embedding_model)

    def encode(self, texts: list[str], batch_size: int = 64) -> list[list[float]]:
        """Return L2-normalized embeddings as plain Python lists."""
        vectors = self._model.encode(
            texts,
            batch_size=batch_size,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return vectors.tolist()

    def encode_one(self, text: str) -> list[float]:
        return self.encode([text])[0]
