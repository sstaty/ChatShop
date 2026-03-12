# ChatShop

Conversational shopping assistant powered by a RAG pipeline.
User describes what they want → semantic search retrieves relevant products → LLM generates a recommendation.

## Architecture

```
INGESTION (one-shot: scripts/ingest.py)
  data/raw/amazon_products.csv
    → data.loader      (chunked pd.read_csv)
    → data.cleaner     (normalize, strip HTML, dedupe → list[Product])
    → embeddings.embedder  (batch encode title+description → vectors)
    → vectorstore.chroma   (upsert to chroma_db/, persisted)

QUERY (per user message)
  Gradio chat input
    → rag.chain.stream(query)
        → rag.retriever.retrieve(query)   (embed → chroma.query → top-5 Products)
        → rag.prompt.build_user_message() (format products into context block)
        → litellm.completion(stream=True) (system prompt + context + query → LLM)
    → Gradio streams tokens back to UI
```

## Setup

**Requirements:** Python 3.12, [uv](https://docs.astral.sh/uv/)

```bash
# 1. Install dependencies
uv sync

# 2. Configure environment
cp .env.example .env
# Edit .env — set LITELLM_API_KEY (OpenAI key) or switch to Ollama

# 3. Download dataset
#    Kaggle: Amazon Products Dataset 2023 → Electronics category
#    Place CSV at: data/raw/amazon_products.csv

# 4. Run ingestion (one-time, ~10-30 min on CPU)
uv run python scripts/ingest.py

# 5. Launch the app
uv run python main.py
```

## Development

```bash
# Install all extras
uv sync --extra dev --extra test --extra lint

# Run tests
uv run pytest --cov=chatshop tests/

# Inspect ChromaDB
uv run python scripts/inspect_chroma.py --query "wireless headphones" --top-k 5
```

## Config

All settings are read from `.env` (see `.env.example`):

| Key | Default | Description |
|---|---|---|
| `LITELLM_MODEL` | `gpt-4o-mini` | LLM model (any LiteLLM-supported string) |
| `LITELLM_API_KEY` | — | API key for the LLM provider |
| `EMBEDDING_MODEL` | `all-MiniLM-L6-v2` | Sentence-transformers model (local) |
| `CHROMA_PERSIST_DIR` | `chroma_db` | ChromaDB storage path |
| `TOP_K_RESULTS` | `5` | Products retrieved per query |

To use a local Ollama model instead of OpenAI, set:
```
LITELLM_MODEL=ollama/llama3.2
LITELLM_API_KEY=
```

## Project Structure

```
src/chatshop/
  config.py          ← pydantic-settings, all env vars
  data/
    models.py        ← Product pydantic model
    loader.py        ← chunked CSV reader
    cleaner.py       ← normalize, filter, dedupe
  embeddings/
    embedder.py      ← sentence-transformers wrapper
  vectorstore/
    chroma.py        ← ChromaDB upsert + query
  rag/
    retriever.py     ← embed query → chroma → Products
    prompt.py        ← system prompt + context builder
    chain.py         ← RAGChain: run() + stream()
  ui/
    gradio_app.py    ← Gradio Blocks, streaming chat
```
