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

## Phase xx - to categorize later

High volume data: get broad data sets (10k + products), clean up, synthetise what's missing (Synthetic Data Augmentation) cleanup, etc.
Tests and evals: Golden dataset. Eval retrieval. Eval hard questions. Eval costs. What else to eval?
Cost optimization: frontier LLM for thinking & reasoning, fine-tuned open-source for simpler tasks, e.g. JSON outputs (use Outlines or Guidance to guarantee proper JSON structure). Deploy on modal.
Proper web Frontend (react.js), backend (fastAPI), vercel + docker for deployment. Add product cards. Dashboards, thinking (?)

