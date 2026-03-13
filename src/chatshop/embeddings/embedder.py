from chatshop.config import settings


class Embedder:
    """Wraps sentence-transformers (local) or OpenAI embeddings (remote).

    Backend is controlled by settings.embedding_backend:
      "local"  → sentence-transformers, runs fully offline, default model all-MiniLM-L6-v2
      "openai" → OpenAI /v1/embeddings via LiteLLM, default model text-embedding-3-small
                 Requires OPENAI_API_KEY in .env.

    Note: OpenRouter does NOT expose an embeddings endpoint — use "openai" for
    cloud embeddings and OpenRouter only for LLM calls.
    """

    def __init__(self, model_name: str | None = None, backend: str | None = None) -> None:
        self._backend = backend or settings.embedding_backend
        self._model_name = model_name or settings.embedding_model
        if self._backend == "local":
            from sentence_transformers import SentenceTransformer
            self._st_model = SentenceTransformer(self._model_name)

    def encode(self, texts: list[str], batch_size: int = 64) -> list[list[float]]:
        """Return L2-normalized embeddings as plain Python lists."""
        if self._backend == "local":
            return self._encode_local(texts, batch_size)
        return self._encode_openai(texts, batch_size)

    def encode_one(self, text: str) -> list[float]:
        return self.encode([text])[0]

    # ── Backends ──────────────────────────────────────────────────────────────

    def _encode_local(self, texts: list[str], batch_size: int) -> list[list[float]]:
        vectors = self._st_model.encode(
            texts,
            batch_size=batch_size,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return vectors.tolist()

    def _encode_openai(self, texts: list[str], batch_size: int) -> list[list[float]]:
        """Call OpenAI /v1/embeddings via LiteLLM (batched to stay within rate limits)."""
        import litellm

        all_vectors: list[list[float]] = []
        for start in range(0, len(texts), batch_size):
            batch = texts[start : start + batch_size]
            response = litellm.embedding(
                model=self._model_name,
                input=batch,
                api_key=settings.openai_api_key or None,
            )
            all_vectors.extend(item["embedding"] for item in response["data"])
        return all_vectors
