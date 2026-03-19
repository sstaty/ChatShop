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

## Two-Layer Architecture

### Layer 1 — LiteLLM Callback (Automatic)

LiteLLM natively supports Langfuse as a success/failure callback. When enabled, every `litellm.completion()` call is auto-logged as a **generation** in Langfuse with:

- Model name, provider
- Full input messages and output content
- Token counts (prompt, completion, total)
- Latency (time to first token, total)
- Estimated cost (based on model pricing)

This requires zero changes to LLM-calling code — just registering the callback at startup.

### Layer 2 — Explicit Trace Hierarchy (Manual)

Layer 1 alone produces a flat list of generations. Layer 2 adds structure: a **trace** per conversation turn, with **spans** for each module call. Langfuse generations from Layer 1 are nested under the correct spans via metadata passthrough.

```
Trace: agent_turn
├── Span: planner
│   └── Generation: litellm (auto-logged)
├── Span: hybrid_search
├── Span: evaluator
│   └── Generation: litellm (auto-logged)
└── Span: conversationist
    └── Generation: litellm (auto-logged, streamed)
```

Each span carries business-level metadata (intent, filters, diagnosis, strategy) — not just raw LLM I/O.

---

## Module Integration

### Span Metadata Per Module

| Module | Span Name | Input Metadata | Output Metadata |
|--------|-----------|---------------|----------------|
| Planner | `planner` | iteration number | action, reasoning_trace |
| QueryRewriter | *(nested inside planner LLM call)* | — | — |
| HybridSearch | `hybrid_search` | semantic_query, filters | candidate_count, result_count |
| Evaluator | `evaluator` | intent_summary, candidate_count | diagnosis, blocking_constraints, reason |
| Conversationist | `conversationist` | mode (synthesize/clarify), strategy, product_count | strategy |

The QueryRewriter's LLM call happens inside `Planner.plan()` and is captured as a separate generation under the planner span by LiteLLM's callback.

---

## Observability Module Design

All Langfuse logic lives in `src/chatshop/infra/observability.py` — a thin wrapper that isolates the Langfuse SDK from the rest of the codebase.

### API Surface

| Function | Purpose |
|----------|---------|
| `langfuse_enabled()` | Check if both API keys are configured |
| `init_observability()` | Register LiteLLM Langfuse callback (once at startup, no-op if disabled) |
| `create_trace(name, session_id, ...)` | Create a Langfuse trace, return trace object or None |
| `create_span(trace, name, input)` | Create a span under a trace, return span object or None |
| `end_span(span, output)` | End a span with optional output metadata |
| `llm_metadata(trace, span)` | Build the `{"trace_id": ..., "parent_observation_id": ...}` dict for LiteLLM |
| `flush_observability()` | Flush pending Langfuse events |

### Graceful Degradation

Every function is safe to call when Langfuse is not configured:

- `langfuse_enabled()` returns False when env vars are empty
- `create_trace` / `create_span` return None
- `end_span` / `flush_observability` are silent no-ops when passed None
- `llm_metadata` returns None, causing `LLMClient` to skip the metadata kwarg
- All functions wrap Langfuse SDK calls in try/except — a broken Langfuse connection never crashes the app

---

## Metadata Threading Pattern

The metadata dict flows through a clean 3-level chain:

```
AgentLoop                          creates trace + span
    → llm_metadata(trace, span)    builds {"trace_id": ..., "parent_observation_id": ...}
    → Module.method(metadata=...)   passes dict through unchanged
        → LLMClient.complete(metadata=...)  merges into litellm kwargs
            → litellm.completion(**kwargs)  Langfuse callback reads metadata
                → Generation nested under correct span in Langfuse
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
| `src/chatshop/infra/observability.py` | All Langfuse wrapper logic |
| `src/chatshop/infra/llm_client.py` | Accepts `metadata` param, passes to litellm |
| `src/chatshop/agent/agent_loop.py` | Creates traces/spans, orchestrates metadata flow |
| `src/chatshop/agent/planner.py` | Threads metadata to LLM call |
| `src/chatshop/rag/query_rewriter.py` | Threads metadata to LLM call |
| `src/chatshop/agent/evaluator.py` | Threads metadata to LLM call |
| `src/chatshop/agent/conversationist.py` | Threads metadata to LLM call |
| `src/chatshop/ui/gradio_app.py` | Calls `init_observability()` at startup |
| `src/chatshop/config.py` | Langfuse env var settings |

---

## Deviations from Plan

### Langfuse version pinned to `<3.0`

LiteLLM 1.82 passes `sdk_integration` as a keyword argument when initialising the Langfuse client (see `litellm/integrations/langfuse/langfuse.py`, line 147). Langfuse 3.x and 4.x removed this parameter from `Langfuse.__init__()`, causing a `TypeError` at runtime.

**Fix:** Pin `langfuse>=2.0,<3.0` in `pyproject.toml`. Langfuse 2.57.x is the latest 2.x release and is fully compatible with LiteLLM 1.82.

**When to revisit:** When upgrading LiteLLM to a version that drops the `sdk_integration` kwarg or adapts to the new Langfuse 3.x/4.x API, bump the langfuse upper bound accordingly.
