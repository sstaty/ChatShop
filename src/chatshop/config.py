from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # LLM — direct provider key (OpenAI, Anthropic, etc.)
    litellm_model: str = "gpt-4o-mini"
    litellm_api_key: str = ""

    # LLM — OpenRouter (routes to any frontier model with one key)
    # Set litellm_model to e.g. "openrouter/openai/gpt-4o-mini" to activate.
    openrouter_api_key: str = ""

    # Embeddings
    # backend: "local" (sentence-transformers, no API key) or "openai" (text-embedding-3-small)
    embedding_backend: str = "local"
    embedding_model: str = "all-MiniLM-L6-v2"
    openai_api_key: str = ""  # used when embedding_backend="openai"

    # Vector store
    chroma_persist_dir: str = "chroma_db"
    chroma_collection: str = "products"

    # Data
    data_raw_dir: str = "data/raw"

    # HuggingFace Hub
    hf_token: str = ""
    hf_dataset_repo: str = ""

    # RAG
    top_k_results: int = 5


settings = Settings()
