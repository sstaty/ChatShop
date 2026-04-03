from openai import OpenAI

from chatshop.config import settings


class Embedder:
    """OpenAI embeddings via /v1/embeddings."""

    def __init__(self, model_name: str | None = None) -> None:
        self._model_name = model_name or settings.embedding_model
        self._client = OpenAI(api_key=settings.openai_api_key or None)

    def encode(self, texts: list[str], batch_size: int = 64) -> list[list[float]]:
        """Return embeddings as plain Python lists, batched to respect rate limits."""
        all_vectors: list[list[float]] = []
        for start in range(0, len(texts), batch_size):
            batch = texts[start : start + batch_size]
            response = self._client.embeddings.create(
                model=self._model_name,
                input=batch,
            )
            all_vectors.extend(item.embedding for item in response.data)
        return all_vectors

    def encode_one(self, text: str) -> list[float]:
        return self.encode([text])[0]
