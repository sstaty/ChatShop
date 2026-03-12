from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # LLM
    litellm_model: str = "gpt-4o-mini"
    litellm_api_key: str = ""

    # Embeddings
    embedding_model: str = "all-MiniLM-L6-v2"

    # Vector store
    chroma_persist_dir: str = "chroma_db"
    chroma_collection: str = "products"

    # Data
    data_raw_dir: str = "data/raw"

    # RAG
    top_k_results: int = 5


settings = Settings()
