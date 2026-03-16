# ChatShop — Agentic Architecture

Living architecture document

---

## System Overview

ChatShop is a conversational shopping assistant designed as an AI engineering portfolio system. Users express product needs in natural language and the system iteratively converges on relevant recommendations using an agentic retrieval loop.

Key architectural principle:

Retrieval produces evidence. The Planner owns reasoning and conversation flow.

The system combines:

- conversational memory
- hybrid retrieval (symbolic filtering + semantic vector search)
- query rewriting
- iterative planning
- explicit retrieval quality evaluation
- reasoning transparency in the UI

The architecture is designed to be domain‑extensible beyond headphones into broader consumer electronics or general product search.

---

## Core Agent Loop

The system behaves as a single conversational agent driven by a central planning module.

```
User → Planner
            ↓
     action routing
            ↓
   clarify | search | respond
```

Loop properties:

- Planner decides the next step at every iteration
- Retrieval never produces the final answer directly
- Evidence is always returned to the Planner
- Loop runs with a strict iteration cap (typically 3)

Reference loop:

```
while not finished:

    plan = planner(history, previous_results, evaluator_feedback)

    if plan.action == "clarify":
        ask_user(plan.question)
        stop

    if plan.action == "search":
        results = hybrid_search(plan.search_plan)
        evaluation = evaluator(results, plan.intent_summary)
        evaluator_feedback = evaluation.reason
        continue

    if plan.action == "respond":
        return generate_final_answer(plan.response_strategy, results)
```

---

## Planner Module Design

The Planner is the central reasoning component responsible for:

- intent interpretation
- retrieval strategy construction
- constraint reasoning
- trade‑off handling
- response strategy selection

### Inputs

- full conversation history
- current user message
- previous retrieval evidence (optional)
- evaluator feedback (optional)

### Output Schema (Discriminated Union)

#### Clarify

```
{
  "action": "clarify",
  "question": string,
  "reasoning_trace": string
}
```

#### Search

```
{
  "action": "search",
  "search_plan": {
      "semantic_query": string,
      "filters": {...},
      "sort_by": "rating" | "price_asc" | "price_desc"
  },
  "reasoning_trace": string
}
```

#### Respond

```
{
  "action": "respond",
  "response_strategy": "final_recommendation" |
                       "tradeoff_explanation" |
                       "no_results" |
                       "informational",
  "reasoning_trace": string
}
```

Design principles:

- Planner always owns conversational state
- Trade‑offs handled during response synthesis
- Planner may respond without additional retrieval
- Planner may iterate retrieval multiple times

---

## Query Rewriting Module

Query rewriting is a dedicated semantic translation layer between user intent and retrieval.

Responsibilities:

- map subjective language to technical attributes
- infer likely constraints (use case, budget sensitivity)
- enrich semantic query phrasing
- generate structured filter hints

Examples:

- "for the gym" → stable fit, sweat resistance, wireless
- "music feels alive" → bass emphasis, warm tuning

This module improves retrieval recall and reduces dependence on embedding similarity alone.

---

## Evaluator Module Design

The Evaluator is a lightweight LLM‑based quality gate executed after retrieval.

It does not control flow. It scores evidence sufficiency.

Primary question:

Is the retrieved evidence set sufficient to confidently answer the user request?

### Output

```
{
  "satisfactory": boolean,
  "reason": string
}
```

Evaluator receives structured context:

- normalized intent summary
- applied constraints
- top‑N product summaries
- candidate count

Reliability techniques:

- binary decision enforcement
- required concrete failure reason
- low temperature configuration
- awareness of constraint satisfaction
- penalizing extremely small candidate sets

Evaluator feedback is injected into the next Planner iteration.

---

## Hybrid Retrieval Strategy

Two‑stage retrieval pipeline:

```
metadata filtering
        ↓
candidate pool
        ↓
vector similarity search
        ↓
ranked top‑N evidence set
```

Benefits:

- symbolic filtering improves precision
- semantic search improves recall

Vector search uses sentence‑transformer embeddings stored in ChromaDB.

---

## Prompt Design Philosophy

LLM prompts act as architectural control surfaces.

Each LLM call has:

- one responsibility
- one decision boundary
- one output schema

Planner prompt characteristics:

- strategic reasoning role
- strong schema enforcement
- awareness of tools and loop constraints
- no deep product ranking or hallucinated details

Evaluator prompt characteristics:

- skeptical judging role
- binary decision focus
- structured evidence presentation
- low creativity configuration

Response synthesis prompt characteristics:

- user‑facing explanation tone
- persuasive but factual recommendation style
- clear trade‑off communication

---

## Terminology

The system is described as a single conversational agent.

Internal components are referred to as modules:

- Planner module
- Evaluator module
- Retrieval module
- Query rewriting module

This avoids artificial multi‑agent complexity while remaining extensible.

---

## Suggested Module Architecture

```
chatshop/

    agent/
        planner.py
        evaluator.py
        agent_loop.py

    retrieval/
        hybrid_search.py
        vector_store.py

    domain/
        query_rewriter.py
        product_schema.py

    ui/
        gradio_app.py
        reasoning_panel.py

    infra/
        llm_client.py
        config.py
```

---

## Domain Generalization Strategy

Architecture is domain‑agnostic.

Scaling requires:

- richer product ontology
- category‑specific metadata schemas
- stronger query rewriting prompts
- evaluator awareness of new constraints

Core agent loop remains unchanged.

---

## Hard Test Queries

Designed to stress reasoning and retrieval robustness.

- "I need something for the gym"
- "Best sound quality wireless under $30"
- "Something for my commute"
- "Headphones that make music feel alive"

Multi‑turn refinement:

- "Show me under $100"
- "Only ones good for calls"
- "Which has the longest battery"

Upgrade reasoning:

- "Best ANC under $150 vs under $300 — is the upgrade worth it?"

---

## Next Steps / Retrieval Quality Roadmap

Planned improvements:

- Query expansion module to improve recall via multiple semantic search variants
- LLM re‑ranking layer to refine ordering of top retrieval candidates
- Retrieval evaluation benchmark dataset and scoring methodology
- Product attribute extraction and normalization for real‑world catalog data
- Potential critic module for deeper reasoning feedback

These upgrades will evolve the system from a strong agentic RAG prototype toward a production‑grade retrieval assistant.

