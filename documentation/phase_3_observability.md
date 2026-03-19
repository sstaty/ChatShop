# ChatShop — Phase 3: Observability with Langfuse

Living architecture document

---

## Why Observability for LLM Apps

In traditional software, logging captures what happened: "user clicked X, function returned Y." In LLM-powered systems, the model is a black box that *reasons* — and reasoning can go wrong in ways that are invisible without structured tracing.

ChatShop's agentic loop makes 3–4 LLM calls per user turn (Planner, QueryRewriter, Evaluator, Conversationist), potentially across 3 iterations. Without observability, when the system gives a bad answer, there is no way to know:

- **Which module went wrong?** Did the Planner choose the wrong action, did the QueryRewriter produce bad filters, or did the Conversationist hallucinate a product?
- **What does each turn actually cost?** Which module burns the most tokens?
- **Where is the latency?** Is the Evaluator bottleneck killing response time?
- **Are retrieval results grounded?** Is the final answer based on search results or fabricated?

Langfuse answers all of these by capturing structured traces with token counts, latency, cost, and custom business metadata for every LLM interaction.

---

## Architecture: Direct Langfuse Integration

LLM calls go through `LLMClient` (OpenAI SDK wrapper) which logs generations directly to Langfuse after each completion. No intermediary callback layers — full control over what gets logged and how it nests.

```
Trace: agent_turn
├── Span: planner
│   └── Generation: planner (logged by LLMClient)
├── Span: hybrid_search (no LLM call — just metadata)
├── Span: evaluator
│   └── Generation: evaluator (logged by LLMClient)
└── Span: conversationist
    └── Generation: conversationist-synthesize (logged by LLMClient)
```

**How it works:**

1. `AgentLoop.stream_with_trace()` creates a Langfuse **trace** per conversation turn
2. Each module call is wrapped in a **span** with business metadata (intent, filters, diagnosis)
3. `LLMClient.complete()` / `stream()` call `log_generation()` after each LLM call, recording model, token counts, full I/O under the trace
4. The metadata dict `{"trace": trace_obj, "generation_name": "planner"}` flows through each module to `LLMClient`

Each span carries business-level metadata — not just raw LLM I/O.

---

## Module Integration

### Span Metadata Per Module

| Module | Span Name | Input Metadata | Output Metadata |
|--------|-----------|---------------|----------------|
| Planner | `planner` | iteration number | action, reasoning_trace |
| QueryRewriter | *(LLM call logged as generation under trace)* | — | — |
| HybridSearch | `hybrid_search` | semantic_query, filters | candidate_count, result_count |
| Evaluator | `evaluator` | intent_summary, candidate_count | diagnosis, blocking_constraints, reason |
| Conversationist | `conversationist` | mode (synthesize/clarify), strategy, product_count | strategy |

The QueryRewriter's LLM call happens inside `Planner.plan()` and is captured as a separate generation under the trace.

---

## Observability Module Design

All Langfuse logic lives in `src/chatshop/infra/observability.py` — a thin wrapper that isolates the Langfuse SDK from the rest of the codebase.

### API Surface

| Function | Purpose |
|----------|---------|
| `langfuse_enabled()` | Check if both API keys are configured |
| `init_observability()` | Initialise Langfuse client (once at startup, no-op if disabled) |
| `create_trace(name, session_id, ...)` | Create a Langfuse trace, return trace object or None |
| `create_span(trace, name, input)` | Create a span under a trace, return span object or None |
| `end_span(span, output)` | End a span with optional output metadata |
| `log_generation(trace, name, model, input, output, usage)` | Log an LLM generation under a trace with token counts |
| `llm_metadata(trace, generation_name)` | Build metadata dict for LLMClient (`{"trace": ..., "generation_name": ...}`) |
| `flush_observability()` | Flush pending Langfuse events |

### Graceful Degradation

Every function is safe to call when Langfuse is not configured:

- `langfuse_enabled()` returns False when env vars are empty
- `create_trace` / `create_span` return None
- `end_span` / `log_generation` / `flush_observability` are silent no-ops when passed None
- `llm_metadata` returns None, causing `LLMClient` to skip Langfuse logging entirely
- All functions wrap Langfuse SDK calls in try/except — a broken Langfuse connection never crashes the app

---

## Metadata Threading Pattern

The metadata dict flows through a clean 3-level chain:

```
AgentLoop                              creates trace + span
    → llm_metadata(trace, "planner")   builds {"trace": trace_obj, "generation_name": "planner"}
    → Module.method(metadata=...)       passes dict through unchanged
        → LLMClient.complete(metadata=...)  calls OpenAI SDK, then log_generation()
            → Generation recorded in Langfuse under the trace
```

All `metadata` parameters default to `None`. When Langfuse is disabled, `llm_metadata` returns None, and the entire chain becomes a no-op with zero overhead.

---

## Configuration

### Required Environment Variables

```env
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_HOST=https://cloud.langfuse.com
```

### Setup Steps

1. Create a free account at [cloud.langfuse.com](https://cloud.langfuse.com)
2. Create a new project
3. Copy the public and secret keys from Settings → API Keys
4. Add them to your `.env` file
5. Start the app — traces appear in the Langfuse dashboard automatically

### Settings Integration

The keys are defined in `src/chatshop/config.py` via pydantic-settings, following the same pattern as all other configuration:

```python
langfuse_public_key: str = ""
langfuse_secret_key: str = ""
langfuse_host: str = "https://cloud.langfuse.com"
```

---

## What the Langfuse Dashboard Shows

For each conversation turn:

- **Trace timeline** — visual breakdown of the full turn with module spans
- **Per-generation details** — model, token counts, latency, cost, full input/output messages
- **Business metadata** — evaluator diagnosis, search filters, response strategy (attached to spans)
- **Cost aggregation** — total cost per trace, per session, per time period
- **Latency analysis** — which modules are slowest, P50/P95/P99 latencies

---

## Files

| File | Role |
|------|------|
| `src/chatshop/infra/observability.py` | All Langfuse wrapper logic + `log_generation()` |
| `src/chatshop/infra/llm_client.py` | OpenAI SDK wrapper, logs generations via `log_generation()` |
| `src/chatshop/agent/agent_loop.py` | Creates traces/spans, orchestrates metadata flow |
| `src/chatshop/agent/planner.py` | Threads metadata to LLM call |
| `src/chatshop/rag/query_rewriter.py` | Threads metadata to LLM call |
| `src/chatshop/agent/evaluator.py` | Threads metadata to LLM call |
| `src/chatshop/agent/conversationist.py` | Threads metadata to LLM call |
| `src/chatshop/ui/gradio_app.py` | Calls `init_observability()` at startup |
| `src/chatshop/config.py` | Langfuse env var settings |

---

## Deviations from Plan

### LiteLLM removed, replaced with direct OpenAI SDK

The original plan used LiteLLM's Langfuse callback for "Layer 1" (automatic generation logging). This caused persistent version incompatibilities:

- LiteLLM 1.82 passed `sdk_integration` kwarg to Langfuse, but Langfuse 3.x/4.x dropped that parameter
- LiteLLM's `existing_trace_id` metadata mechanism was needed instead of `trace_id` for trace nesting
- LiteLLM didn't support `parent_observation_id` for span nesting at all

**Resolution:** Removed LiteLLM entirely. Replaced with:
- **OpenAI SDK** for LLM calls (supports OpenAI + OpenRouter via `base_url`)
- **Direct Langfuse `log_generation()`** calls from `LLMClient` after each completion

This gives better control, simpler debugging, and eliminates the dependency compatibility issues. The `langfuse>=2.0,<3.0` pin remains as a precaution but can likely be relaxed now that LiteLLM is no longer in the picture.

### Deprecated `rag/chain.py` deleted

Phase 1's `RAGChain` was the last file importing litellm directly. It was already marked as deprecated and superseded by `AgentLoop`. Deleted along with its test file `tests/test_chain.py`.
