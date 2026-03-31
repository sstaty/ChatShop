from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # API keys
    # openai_api_key: used for OpenAI LLM calls and embeddings
    # openrouter_api_key: used when any model string starts with "openrouter/"
    openai_api_key: str = ""
    openrouter_api_key: str = ""

    # LLM models — one per component.
    # Direct OpenAI: "gpt-4o-mini", "gpt-4o"
    # OpenRouter:    "openrouter/openai/gpt-4o", "openrouter/anthropic/claude-3.5-haiku"
    planner_model: str = "gpt-4o-mini"          # decision logic — use smartest model
    query_rewriter_model: str = "gpt-4o-mini"   # structured JSON extraction
    evaluator_model: str = "gpt-4o-mini"         # binary result classification
    synthesis_model: str = "gpt-4o-mini"         # final response generation

    # Embeddings
    # backend: "local" (sentence-transformers, no API key) or "openai" (text-embedding-3-small)
    embedding_backend: str = "local"
    embedding_model: str = "all-MiniLM-L6-v2"

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

    # Langfuse observability (optional — leave blank to disable)
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_host: str = "https://cloud.langfuse.com"

    # Evals
    eval_judge_model: str = "gpt-4o-mini"


settings = Settings()
