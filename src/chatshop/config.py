from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # LLM API keys
    # litellm_api_key: used for direct provider calls (OpenAI, Anthropic, etc.)
    # openrouter_api_key: used when any model string starts with "openrouter/"
    litellm_api_key: str = ""
    openrouter_api_key: str = ""

    # LLM models — one per component. Any LiteLLM model string works.
    # "openrouter/..." models use openrouter_api_key; others use litellm_api_key.
    planner_model: str = "gpt-4o-mini"          # decision logic — use smartest model
    query_rewriter_model: str = "gpt-4o-mini"   # structured JSON extraction
    evaluator_model: str = "gpt-4o-mini"         # binary result classification
    synthesis_model: str = "gpt-4o-mini"         # final response generation

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
