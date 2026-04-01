# Task 1 — Typed SSE events (backend)

## Context

ChatShop is an agentic headphone shopping assistant. The backend is FastAPI + Python.
The agent loop (`backend/src/chatshop/agent/agent_loop.py`) currently yields two types:
- `TraceEvent(text: str)` — human-readable reasoning strings
- `str` — raw response tokens from the conversationist LLM

The `/chat` FastAPI endpoint streams these via SSE as `data: <text>\n\n` blobs.

The frontend currently receives undifferentiated text and has to guess what each chunk means.

## Goal

Replace the current untyped SSE stream with **typed JSON events**. Every SSE frame must
carry a `type` field so the frontend can route each event to the right UI component without
parsing or guessing.

Do NOT change any LLM calls, search logic, or evaluation logic. This is purely a
structural change to what gets yielded and how it is serialised.

---

## Typed event schema

Define these as Pydantic models in a new file:
`backend/src/chatshop/api/sse_events.py`

```python
from typing import Literal, Any
from pydantic import BaseModel

class ThinkingEvent(BaseModel):
    type: Literal["thinking"] = "thinking"
    message: str        # short human-readable status, e.g. "Decoding your vibe..."
    detail: str = ""    # optional subtitle, e.g. "figuring out what you actually want"

class IntentEvent(BaseModel):
    type: Literal["intent"] = "intent"
    summary: str        # plan.intent_summary
    semantic_query: str # sp.semantic_query
    filters: dict[str, Any]  # structured: {"max_price": 200, "wireless": False, ...}

class ProductsEvent(BaseModel):
    type: Literal["products"] = "products"
    items: list[dict]   # list of Product dicts, each with an added "badge" field

class ResponseChunkEvent(BaseModel):
    type: Literal["response_chunk"] = "response_chunk"
    text: str           # single token or small chunk from conversationist

class ClarifyEvent(BaseModel):
    type: Literal["clarify"] = "clarify"
    # no extra fields — tokens follow as response_chunk events

class DoneEvent(BaseModel):
    type: Literal["done"] = "done"

class ErrorEvent(BaseModel):
    type: Literal["error"] = "error"
    message: str

SSEEvent = ThinkingEvent | IntentEvent | ProductsEvent | ResponseChunkEvent | ClarifyEvent | DoneEvent | ErrorEvent
```

---

## Changes to agent_loop.py

Convert `stream_with_trace` to yield typed events instead of `TraceEvent | str`.

Map current yields to new events:

| Current yield | New event |
|---|---|
| `TraceEvent("Analyzing request...")` | `ThinkingEvent(message="Analyzing request...", detail="")` |
| `TraceEvent("Clarifying...")` | `ClarifyEvent()` then response tokens as `ResponseChunkEvent` |
| `TraceEvent("Generating response...")` | `ThinkingEvent(message="Generating response...")` |
| Intent/semantic/filter TraceEvent (search step) | `IntentEvent(summary=..., semantic_query=..., filters=...)` |
| Retrieved N candidates TraceEvent | `ThinkingEvent(message="Evaluating results...", detail=f"{n} candidates found")` |
| Raw str tokens from conversationist | `ResponseChunkEvent(text=token)` |
| End of generator | `DoneEvent()` |

### Badge assignment for ProductsEvent

After search completes and before responding, assign one badge per product.
Use a simple heuristic — no LLM call needed:

```python
def _assign_badges(products: list[Product]) -> list[dict]:
    if not products:
        return []
    dicts = [p.model_dump() for p in products]
    # sort by price to find cheapest and most expensive
    by_price = sorted(range(len(dicts)), key=lambda i: dicts[i]["price"])
    cheapest_idx = by_price[0]
    priciest_idx = by_price[-1]
    # find highest rated (if rating field exists, else fallback to best match)
    ratings = [d.get("rating", 0) for d in dicts]
    best_idx = ratings.index(max(ratings))
    for i, d in enumerate(dicts):
        if i == priciest_idx:
            d["badge"] = "luxury pick"
        elif i == cheapest_idx:
            d["badge"] = "best value"
        elif i == best_idx:
            d["badge"] = "best match"
        else:
            d["badge"] = "recommended"
    return dicts
```

Emit `ProductsEvent` immediately after search + evaluation completes (before the
conversationist runs), so the frontend can show cards while the text response streams in.

### Thinking message copy

Add a helper dict for human-friendly status messages (frontend will display these):

```python
THINKING_MESSAGES = {
    "analyzing":   ("Decoding your request...",    "figuring out what you want"),
    "searching":   ("Scanning the catalogue...",   "running hybrid search"),
    "evaluating":  ("Checking quality...",         "evaluator quality gate"),
    "responding":  ("Crafting your answer...",     "almost there"),
    "clarifying":  ("Need a bit more info...",     ""),
}
```

Use these when emitting `ThinkingEvent` at each stage.

---

## Changes to the FastAPI /chat endpoint

Update the SSE serialiser to handle typed events:

```python
async def event_stream(request: ChatRequest):
    try:
        for event in agent_loop.stream_with_trace(request.message, request.history):
            yield f"data: {event.model_dump_json()}\n\n"
        yield f"data: {DoneEvent().model_dump_json()}\n\n"
    except Exception as e:
        yield f"data: {ErrorEvent(message=str(e)).model_dump_json()}\n\n"
```

---

## What NOT to change

- No changes to `Planner`, `Evaluator`, `HybridSearch`, `Conversationist`
- No changes to LangFuse observability calls
- No changes to `AgentResult` or `run_with_result` (used by evals)
- No changes to the eval golden dataset or LLM-as-judge logic
- Keep `TraceEvent` class in place if it is imported by tests — deprecate with a comment

---

## Verification

After the change, manually test via curl:

```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "I want waterproof running headphones under $150", "history": []}' \
  --no-buffer
```

Expected output — a sequence of SSE frames, each parseable as JSON, with `type` field:
1. `{"type":"thinking","message":"Decoding your request...","detail":"..."}`
2. `{"type":"intent","summary":"...","semantic_query":"...","filters":{...}}`
3. `{"type":"thinking","message":"Checking quality...","detail":"..."}`
4. `{"type":"products","items":[...]}` — each item has a `badge` field
5. `{"type":"thinking","message":"Crafting your answer...","detail":"..."}`
6. N × `{"type":"response_chunk","text":"..."}` — streamed tokens
7. `{"type":"done"}`

If the agent clarifies instead of searching:
1. `{"type":"thinking",...}`
2. `{"type":"clarify"}`
3. N × `{"type":"response_chunk","text":"..."}`
4. `{"type":"done"}`

Run existing evals after the change to confirm `run_with_result` is unaffected.
