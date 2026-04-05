# Overview

This live document serves as a main planning document for develpoment phases. It's purpose is to plan the development, have an overview of different phases, and to help understand Claude Code these different implementation goals (see [CLAUDE.md](../CLAUDE.md))

Note: we use markdown files in repo to track history and allow Claude to read it easily.

## Phase 1
The Core for ChatShop project: 
- core project structure
- data manipulation - tested on a synthethic data (100 headphone products created with claude sonnet 4.5)
- embeddings with openai & huggingface, chromaDB for vectorstore
- RAG to retrieve closest matches
- chat interface with gradio UI
- Here you can find [Basic RAG](phase_1_basic_rag)


## Phase 2 
Advanced replies with agentic AI.
- multi-agent workflow to get better conversation handling and best-matching products
- handling edge-cases such as vague prompts & questions, transforming generic requirements to concrete product specs, etc:
    - "I need something for the gym" — too vague, earbuds? over-ear? what matters to them?
    - "Best headphones for my commute" — commute could mean subway (ANC critical), cycling (situational awareness needed — opposite of ANC!)
    - "Completely waterproof headphones with 50 hour battery under $50" — likely impossible, needs graceful handling
- handling multi-criteria ranking:
    - "I do both long flights and morning runs — what's the best single pair that handles both?" — travel and sport have partially conflicting requirements (comfort/ANC vs secure fit/sweat resistance)
    - "Compare the best ANC headphone under $150 vs the best one under $300 — is the upgrade worth it?"
- Here you can find the [Agentic AI architecture](phase_2_agentic_architecture.md)

## Phase 3
LLM Observability with Langfuse. Also: replaced LiteLLM with direct OpenAI SDK.
- Structured traces per conversation turn: Trace(agent_turn) → Span(planner/search/evaluator/conversationist) → Generation
- Direct Langfuse generation logging from LLMClient (no callback intermediary)
- Business metadata on spans: evaluator diagnosis, search filters, response strategy, candidate counts
- Cost, latency, and token tracking per module and per turn
- Graceful degradation: fully optional, zero impact when Langfuse env vars are absent
- Removed LiteLLM dependency — all LLM calls now use OpenAI SDK directly (supports OpenAI + OpenRouter via base_url)
- Deleted deprecated Phase 1 RAGChain (`rag/chain.py`)
- Here you can find the [Observability Architecture](phase_3_observability.md)

## Phase 4
LLM Evaluation System. End-to-end evals of actual LLM behavior against a curated golden dataset.
- 5-layer evaluation: deterministic checks (action routing, filter extraction, response strategy) as hard asserts; LLM-as-judge (retrieval relevance, response quality) as reported metrics
- 25-case golden dataset in typed Python dataclasses covering: clear search, clarify, informational, off-topic, edge cases, and multi-turn conversations
- Pipeline runner with `AgentResult` + `run_with_result()` exposing structured intermediate state (planner output, search results, evaluator output)
- Cache layer keyed by `(case_id, model_config_hash)` — iterate on judge prompts without re-running expensive pipeline
- LLM-as-judge scoring 4 dimensions: groundedness, helpfulness, personality, constraint adherence (1-5 scale, report only)
- Markdown reports auto-saved to `tests/evals/results/` with model config + accuracy + cost + latency for side-by-side comparison
- `@pytest.mark.eval` marker keeps evals out of default test runs; explicit trigger: `uv run pytest -m eval -v`
- Here you can find the [Evaluation System Architecture](phase_4_evals.md)

## Phase 5
Web frontend (Next.js + TypeScript) and FastAPI backend integration.

- **Task 1 — Typed SSE events**: replaced untyped text stream with structured JSON events (`thinking`, `intent`, `products`, `response_chunk`, `clarify`, `done`, `error`). Badge assignment added server-side. Pydantic models in `backend/src/chatshop/api/sse_events.py`.
- **Task 2 — Layout shell & SSE consumer**: 4-state machine (`idle → thinking → intent → results / clarify`) in `agentState.ts`. `useAgentStream` hook consumes the SSE stream and drives layout transitions. Two-zone layout: top zone (intent chips → product cards) + bottom chat zone. Full mobile responsiveness.
- **Task 3 — Product cards & chat zone redesign**: real `ProductCard` component with badge colors, type images, and key-attr chips. Orb moved into the chat zone. Chat zone phases: thinking (orb), streaming (text), input (done). Latest assistant message shown above input. Contextual input placeholder per state. Card stagger animation on entry; dissolve on new message.

See task files: [task1](task1_typed_sse_events.md), [task2](task2_layout_shell_sse.md), [task3](task3_product_cards_chat_zone.md)

## Phase xx - to categorize later

High volume data: get broad data sets (10k + products), clean up, synthetise what's missing (Synthetic Data Augmentation) cleanup, etc.
Tests and evals: Golden dataset. Eval retrieval. Eval hard questions. Eval costs. What else to eval?
Cost optimization: frontier LLM for thinking & reasoning, fine-tuned open-source for simpler tasks, e.g. JSON outputs (use Outlines or Guidance to guarantee proper JSON structure). Deploy on modal.
Proper web Frontend (react.js), backend (fastAPI), vercel + docker for deployment. Add product cards. Dashboards, thinking (?)

## Latest Implementation Notes
- Frontend baseline chat page is now functional in `frontend/src/app/page.tsx`.
- It supports input + send button + message list, and posts to `http://localhost:8000/chat`.
- Backend response is appended to the same message list.
- Added basic modern chatbot visuals: light blue page background, centered rounded chat container, message bubbles, and styled input/send controls.
- FastAPI `/chat` is now wired to the real `AgentLoop` using the non-streaming `run_with_result()` path.
- The Gradio streaming path is preserved and now shares the same runtime loop construction helper as the FastAPI app.

