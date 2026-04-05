# ChatShop

Conversational shopping assistant — powered by RAG and Agentic AI.
Live demo on a headphones dataset: https://chatshop.statelov.dev

---

## What it does

> "Why browse categories and apply filters — when you can just say what you want?"

ChatShop is a conversational product discovery assistant. Describe what you need, get the best matches. Vague about what you want? It asks follow-up questions. Currently a headphones demo — but the architecture generalises to any e-commerce catalogue.

---

## Architecture

```
User message
     │
  Planner ──────────────────────────────────-────────┐
  (clarify | search | respond)                       │
     │                                               │
     ├─ CLARIFY → Conversationist (clarify mode)     │
     │                                               │
     └─ SEARCH                                       │
          │                                          │
     QueryRewriter                                   │
     (intent → semantic query + filters)             │
          │                                          │
     HybridSearch                                    │
     (metadata filter + vector similarity)           │
          │                                          │
     Evaluator                                       │
     (sufficient | narrow | no_results)              │
          │                                          │
     Curator                                         │
     (select ≤3 products, assign badges + rationale) │
          │                                          │
     Conversationist ←──────────────────────-────────┘
     (synthesize final response)
          │
     SSE stream → Next.js frontend
```

**Components:**

- **Planner** (`agent/planner.py`) — central brain. Given conversation history and evaluator feedback, decides the next action: clarify, search, or respond. Structured output: `ClarifyAction | SearchAction | RespondAction`.
- **QueryRewriter** (`rag/query_rewriter.py`) — translates natural language into a semantic query and typed filters (price, wireless, ANC, type, battery). Conservative: doesn't infer filters not explicitly stated.
- **HybridSearch** (`rag/hybrid_search.py`) — two-stage retrieval: convert filters to a metadata `where` clause, then rank remaining candidates by cosine similarity to the semantic query.
- **Evaluator** (`agent/evaluator.py`) — quality gate. Deterministic diagnosis (`no_results` / `narrow_results` / `sufficient`) plus LLM-identified blocking constraints. Feeds back into the planner on retry.
- **Curator** (`agent/curator.py`) — selects up to 3 products, assigns a badge ("best match", "best value", "luxury pick", "hidden gem"), writes a 1-2 sentence rationale, and generates 2-4 key-attribute chips per product.
- **Conversationist** (`agent/conversationist.py`) — final response synthesis. Strategy-aware: catalog recommendation, tradeoff explanation, narrow/no results, informational, off-topic — each handled differently.
- **AgentLoop** (`agent/agent_loop.py`) — orchestrates all components, streams typed SSE events to the frontend, runs up to 3 iterations.

---

## Tech Stack

| Layer | Tech | Why |
|---|---|---|
| LLM routing | OpenAI SDK + OpenRouter | One client, swap any model via env var — OpenAI, Claude, Gemini, DeepSeek, Ollama |
| Embeddings | `all-MiniLM-L6-v2` (local) / `text-embedding-3-small` (OpenAI) | Local default = zero cost, no API key needed during dev |
| Vector store | NumpyStore (JSON-persisted) / ChromaDB | NumpyStore is serverless-friendly — no Docker, no infra overhead |
| Backend | FastAPI + Pydantic v2 | Typed, fast, SSE support built-in |
| Frontend | Next.js 16 + React 19 + Tailwind CSS 4 | SSE streaming via `ReadableStream`; typed event dispatch |
| Observability | Langfuse | Per-span traces, token cost, latency per component — fully optional, zero impact when absent |
| Data | Synthetic headphones dataset (100 products) | Claude-generated from real product attributes; clean schema, no scraping/licensing issues |

---

## Key Design Decisions

1. **Planner as the single decision point.** All routing logic lives in one structured-output LLM call. Every iteration has a logged action and reason — no spaghetti if/else chains.

2. **Hybrid search (semantic + metadata filters).** Pure vector search lets "under $150" slip through as vibes; pure keyword filtering misses synonyms. Two-stage retrieval handles both structured constraints and semantic intent.

3. **Evaluator feedback loop.** Instead of silently returning bad results, the evaluator classifies sufficiency and identifies which filter is blocking results. The planner retries with a broadened query — the system is self-correcting.

4. **Synthetic data strategy.** 100 headphones generated with Claude Sonnet, seeded from real product attributes and price distributions. Gives full control over schema completeness without scraping or licensing issues during prototyping.

5. **Per-component model assignment.** Different tasks need different quality/cost tradeoffs. The planner uses a stronger model; evaluator and query-rewriter use a cheaper one. Eval results confirmed this split delivers the best cost-to-quality ratio.

---

## Evals

25-case golden dataset covering: clear search, clarify, informational, off-topic, impossible-constraint edge cases, and multi-turn conversations.

Three evaluation layers:
- **Deterministic checks** — action routing, filter extraction, response strategy (JSON parse + assert)
- **LLM-as-a-judge** — gpt-4o-mini scores groundedness, helpfulness, personality, constraint adherence (1–5 scale)
- **Cost and latency** measured per agent loop

| Config | Action Routing | Filter Extraction | Response Strategy | Judge Score | Cost/loop | Latency |
|---|---|---|---|---|---|---|
| gpt-4o-mini (all) | 68% | 100% | 85.7% | 3.7 | 0.034¢ | 7.4s |
| gpt-4o (all) | 84% | 100% | 100% | 4.1 | 0.72¢ | 9.4s |
| Claude Haiku 4.5 (all) | 96% | 83.3% | 100% | 4.3 | 0.344¢ | 12.8s |
| DeepSeek Chat (all) | 80% | 88.9% | 100% | 3.9 | 0.06¢ | 20.5s |
| **gpt-5.4-mini (planner) + gpt-4o-mini (rest)** | **80%** | **100%** | **100%** | **4.0** | **0.129¢** | **7.2s** |
| Claude Haiku (planner) + gpt-4o-mini (rest) | 96% | 91.7% | 100% | 4.2 | 0.166¢ | 12.8s |

**Winner: gpt-5.4-mini (planner) + gpt-4o-mini (everything else)** — 5.6× cheaper than gpt-4o at 98% of the quality. Full results in [`documentation/eval_model_comparison.md`](documentation/eval_model_comparison.md).

---

## Run Locally

```bash
git clone <repo>
cd ChatShop/backend
uv sync
cp .env.example .env        # add OPENAI_API_KEY at minimum
uv run python -m chatshop.scripts.ingest   # embed & index products (one-time)
uvicorn main:app --reload   # http://localhost:8000
```

```bash
cd ChatShop/frontend
npm install
npm run dev                 # http://localhost:3000
```

Required env var: `OPENAI_API_KEY`. Everything else has defaults (local embeddings, NumpyStore). Langfuse vars are optional.

---

## What I'd do next

- Expand to a real product catalogue — Amazon dataset ingestion pipeline is already scaffolded
- Multi-category support — same agent architecture, different datasets and filter schemas
- Cost optimisation — fine-tuned open-source model for evaluator/query-rewriter JSON outputs (Outlines or Guidance for structured generation)
- Richer evals — retrieval precision at K, multi-turn coherence, cost regression tests in CI

---

## Deployment

Frontend on Vercel, backend on a cloud host. The Next.js app proxies `/api/chat` to the FastAPI SSE endpoint. CORS configured for the Vercel domain.
