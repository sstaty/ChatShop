# ChatShop — Phase 4: Evaluation System

Living architecture document

---

## Why Evals

ChatShop has solid unit tests for loop control logic (mocked LLM), but no end-to-end evaluation of actual LLM behavior. When the Planner misroutes a query, the QueryRewriter extracts wrong filters, or the Conversationist hallucinates a product — unit tests with mocked LLM calls cannot catch it.

The eval system tests the real pipeline against a curated golden dataset using two complementary methods:

- **Deterministic checks** for structured outputs (action routing, filter extraction, response strategy)
- **LLM-as-judge** for subjective quality (groundedness, helpfulness, personality, constraint adherence)

Key principle:

Deterministic layers assert. Judge layers report.

This prevents flaky CI while catching real regressions in LLM behavior.

---

## Architecture: 5-Layer Evaluation

```
Layer 1: Action Routing        ── deterministic match  ── hard assert
Layer 2: Filter Extraction     ── deterministic + tol  ── hard assert
Layer 3: Response Strategy     ── deterministic match  ── hard assert
Layer 4: Retrieval Relevance   ── LLM judge (1-5)     ── report only
Layer 5: Response Quality      ── LLM judge (1-5 x4)  ── report only
```

| Layer | What it checks | Method | Pass/Fail? |
|-------|---------------|--------|------------|
| 1. Action routing | Did the Planner pick clarify/search/respond correctly? | Exact match against expected action | Hard assert |
| 2. Filter extraction | Did the QueryRewriter extract the right SearchFilters? | Per-field comparison with tolerance | Hard assert |
| 3. Response strategy | Did the Planner pick the right response strategy? | Exact match against expected strategy | Hard assert |
| 4. Retrieval relevance | Are the returned products relevant to the query? | LLM judge scores 1-5 | Report only |
| 5. Response quality | Is the final response grounded, helpful, on-character? | LLM judge scores 1-5 on 4 dimensions | Report only |

Layers 1-3 test the structured reasoning pipeline. These should be deterministic and reliable — failures indicate real bugs.

Layers 4-5 test subjective quality. LLM judge scores are inherently noisy. They are collected and reported as aggregates, never used as pass/fail assertions.

---

## Golden Dataset

### Schema

The golden dataset is a Python file (`tests/evals/golden_dataset.py`) with typed dataclasses, not JSON or YAML. This gives type checking, IDE autocomplete, inline comments per case, and the ability to use `field(default_factory=...)` for history lists.

```python
@dataclass
class EvalCase:
    # Identity
    id: str                          # e.g. "search_budget_wireless_01"
    category: str                    # e.g. "clear_search", "clarify", "edge_case"
    description: str                 # Human-readable description

    # Input
    query: str                       # The user message
    history: list[dict]              # Prior turns in OpenAI message format (empty for single-turn)

    # Deterministic expectations
    expected_action: Literal["clarify", "search", "respond"]
    expected_filters: dict | None    # Mirrors SearchFilters structure; None for non-search cases
    expected_response_strategy: str | None  # Only for respond cases

    # LLM-as-judge context
    intent_description: str          # What the user actually wants (for judge grounding)
    quality_notes: str               # Hints for the judge about what a good response includes
```

### Field details

`expected_filters` mirrors the `SearchFilters` dataclass structure:

```python
{
    "max_price": 80.0,
    "min_price": None,
    "extra_filters": {"wireless": True}
}
```

Only populated for cases where `expected_action == "search"`. Fields not specified in the dict are not checked (missing = "don't care").

`expected_response_strategy` is one of: `catalog_with_recommendation`, `tradeoff_explanation`, `narrow_results`, `no_results`, `informational`, `off_topic`. Only populated when `expected_action == "respond"`.

`history` uses OpenAI message format for multi-turn cases:

```python
[
    {"role": "user", "content": "I need wireless earbuds"},
    {"role": "assistant", "content": "What's your budget range?"},
]
```

`intent_description` and `quality_notes` are free-text context for the LLM judge. They describe what the user actually wants and what a good response should include, without leaking the expected output.

### Case Categories (~25 total)

#### Clear Search Queries (8 cases)

Queries where the user provides enough context for a search. Tests filter extraction across various constraint combinations.

| ID | Query | Expected Action | Key Filters |
|---|---|---|---|
| `search_01` | "wireless earbuds for running under $80" | search | max_price=80, wireless=True |
| `search_02` | "best noise cancelling headphones under $200" | search | max_price=200, anc=True |
| `search_03` | "wired over-ear headphones" | search | wireless=False, type="over-ear" |
| `search_04` | "open-back headphones for mixing" | search | type="open-back" |
| `search_05` | "cheap bluetooth earbuds" | search | wireless=True (no price — "cheap" is subjective) |
| `search_06` | "top-rated wireless earbuds under $150" | search | max_price=150, wireless=True |
| `search_07` | "earbuds with at least 8 hours battery" | search | min_battery_hours=8 |
| `search_08` | "ANC headphones between $100 and $250" | search | min_price=100, max_price=250, anc=True |

These test the QueryRewriter's conservative inference rule: only extract filters from explicit user statements. "Cheap" should not become a price filter. "Running" should not infer in-ear type.

#### Ambiguous / Clarify Queries (5 cases)

Queries missing both budget AND form factor/type, triggering the clarify action.

| ID | Query | Expected Action | Why Clarify |
|---|---|---|---|
| `clarify_01` | "I need something for the gym" | clarify | No budget, no type |
| `clarify_02` | "I need new earbuds" | clarify | No use case, no budget |
| `clarify_03` | "headphones for my daughter" | clarify | No budget, no type, no use case |
| `clarify_04` | "something for commuting" | clarify | No budget, could be over-ear or in-ear |
| `clarify_05` | "I'm looking for a good pair of headphones" | clarify | Completely generic |

Per the Planner's clarify rules: clarify triggers when BOTH budget AND form factor are completely absent. If either is present, or if the use case strongly implies a form factor, the system should search instead.

#### Informational Queries (3 cases)

Educational questions that should produce a respond/informational action without retrieval.

| ID | Query | Expected Action | Expected Strategy |
|---|---|---|---|
| `info_01` | "what is ANC?" | respond | informational |
| `info_02` | "what's the difference between open-back and closed-back?" | respond | informational |
| `info_03` | "do I need a DAC for wireless headphones?" | respond | informational |

#### Off-Topic Queries (3 cases)

Non-audio queries and greetings that should produce a respond/off_topic action.

| ID | Query | Expected Action | Expected Strategy |
|---|---|---|---|
| `offtopic_01` | "hey" | respond | off_topic |
| `offtopic_02` | "can you recommend a good laptop?" | respond | off_topic |
| `offtopic_03` | "what's the weather like?" | respond | off_topic |

#### Edge Cases (3 cases)

Queries with unrealistic, contradictory, or impossible constraints. Tests how gracefully the system handles failure.

| ID | Query | Expected Action | Notes |
|---|---|---|---|
| `edge_01` | "best sound quality under $20" | search | Extremely tight budget — may result in no_results or narrow_results strategy |
| `edge_02` | "wireless ANC open-back headphones" | search | Contradictory — open-back ANC essentially does not exist |
| `edge_03` | "waterproof over-ear headphones for swimming" | search | Nearly impossible requirement combination |

For edge cases, the expected action is `search` (the system should try), but the response strategy is not strictly asserted — the system might reasonably choose `no_results`, `narrow_results`, or `tradeoff_explanation`.

#### Multi-Turn Conversations (3 cases)

Queries that depend on conversation history. Tests context resolution and search refinement.

| ID | History Context | Query | Expected Action |
|---|---|---|---|
| `multi_01` | Assistant asked about budget | "under $100" | search (filters should include max_price=100) |
| `multi_02` | Search returned results | "which has the longest battery?" | respond (tradeoff_explanation) |
| `multi_03` | User asked "wireless earbuds under $80", got results | "only ones good for calls" | search (refinement with additional constraint) |

Multi-turn cases require `history` to be populated with prior conversation turns in OpenAI message format.

---

## Pipeline Runner

### Problem

`AgentLoop.run()` returns only the final response string. Evals need intermediate state: which action the Planner chose, what filters were extracted, which products were retrieved, and the Evaluator's diagnosis.

### Solution

Add a `run_with_result()` method to `AgentLoop` that returns a structured result alongside the response.

```python
@dataclass
class AgentResult:
    planner_output: PlannerOutput          # First planner decision
    search_results: list[Product] | None   # Products from search (if any)
    evaluator_output: EvaluatorOutput | None
    final_response: str                    # The synthesized text
    iterations: int                        # How many loop iterations ran
```

This is a small addition (~20-25 lines) to `agent_loop.py`. It collects the same data that `stream_with_trace` already produces, just in structured form instead of yielded `TraceEvent` objects.

### Caching

Running 25 cases through the full pipeline means ~100 LLM calls (Planner + QueryRewriter + Evaluator + Conversationist per case). At ~$0.02/case with gpt-4o-mini, a full run costs ~$0.50.

To iterate cheaply on judge prompts or deterministic checks without re-running the pipeline:

- Cache pipeline outputs by `(case_id, model_config_hash)` in `tests/evals/.cache/{case_id}.json`
- On cache hit: skip pipeline, only run judge
- Environment variable `EVAL_REFRESH=1` forces cache refresh

---

## Deterministic Metrics

### Action Routing Check

```python
def check_action(expected: str, actual: PlannerOutput) -> bool:
    return actual.action == expected
```

Binary pass/fail. This is the most critical check — if routing is wrong, everything downstream is meaningless.

### Filter Extraction Check

```python
def check_filters(expected: dict, actual: SearchFilters) -> dict[str, bool]:
    """Per-filter comparison with tolerance rules."""
```

Comparison rules:

| Filter Type | Comparison Method |
|---|---|
| Price (max_price, min_price) | Within 10% or $5, whichever is larger |
| Booleans (wireless, anc) | Exact match |
| Strings (type) | Exact match |
| Integers (min_battery_hours) | Within 1 hour |

False positive detection: if expected does not specify a filter but actual includes it, flag as a warning (the system inferred a constraint the user did not state). This is important for enforcing the QueryRewriter's conservative inference principle.

Only evaluated when `expected_action == "search"` AND the planner actually returned search.

### Response Strategy Check

```python
def check_strategy(expected: str, actual: RespondAction) -> bool:
    return actual.response_strategy == expected
```

Only evaluated when `expected_action == "respond"`.

---

## LLM-as-Judge

### Judge Model

Uses the existing `LLMClient` — no new dependencies. Configurable via `Settings.eval_judge_model`, default `gpt-4o-mini`.

### Scoring Schema

Pydantic model for structured LLM output, following the same pattern as `_EvaluatorSchema` and `_PlannerSchema`:

```python
class JudgeScores(BaseModel):
    groundedness: int           # 1-5
    groundedness_reason: str
    helpfulness: int            # 1-5
    helpfulness_reason: str
    personality: int            # 1-5
    personality_reason: str
    constraint_adherence: int   # 1-5
    constraint_adherence_reason: str
```

### Scoring Rubric

#### Groundedness (1-5)

- 5: Every product mentioned appears in the retrieved set. All specs and prices are accurate.
- 4: Products are from the retrieved set. Minor spec details may be paraphrased but not fabricated.
- 3: Products are from the retrieved set but some specs are slightly off or embellished.
- 2: Most products exist but some details are clearly fabricated.
- 1: Hallucinated products or invented specifications.

#### Helpfulness (1-5)

- 5: Directly addresses the user's intent, provides actionable recommendation with clear reasoning.
- 4: Addresses the intent with a useful recommendation but reasoning could be stronger.
- 3: Addresses the intent but lacks specificity or reasoning.
- 2: Partially relevant but misses key aspects of what the user asked for.
- 1: Generic response that could apply to any query.

#### Personality (1-5)

- 5: Sounds like the ChatShop character — witty, knowledgeable friend who happens to know headphones, not a product manual.
- 4: Warm and engaging with some character.
- 3: Professional but bland.
- 2: Overly formal or robotic.
- 1: Reads like a database dump.

#### Constraint Adherence (1-5)

- 5: Respects all user constraints (budget, features, type). If constraints were impossible, explains clearly why.
- 4: Respects most constraints with minor deviations explained.
- 3: Partially addresses constraints, misses one.
- 2: Ignores some stated constraints.
- 1: Recommends products that violate stated constraints without acknowledgment.

### Judge Prompt

The judge receives structured context:

```
You are evaluating a headphone shopping assistant's response.

## User Query
{query}

## Conversation History
{history}

## User's Intent
{intent_description}

## Retrieved Products (what the system had available)
{products_context}

## Assistant Response
{response}

## Quality Notes
{quality_notes}

Score each dimension 1-5 with a one-sentence reason.
```

### Clarify Case Rubric

For cases where `expected_action == "clarify"`, use a simplified two-dimension rubric:

- **Helpfulness** (1-5): Did the clarifying question target the right missing information? Does it help narrow the search efficiently?
- **Personality** (1-5): Does it sound like ChatShop — warm, conversational, not interrogative?

Groundedness and constraint adherence are not applicable to clarify cases.

---

## Test Integration

### File Structure

```
tests/evals/
    __init__.py
    conftest.py              # Real AgentLoop fixture (mirrors gradio_app._get_agent_loop wiring)
    golden_dataset.py        # EvalCase dataclass + GOLDEN_CASES list
    judge.py                 # LLM-as-judge: JudgeScores model, judge prompt, scoring logic
    metrics.py               # Deterministic comparison functions
    runner.py                # Pipeline execution + caching + Langfuse cost/latency collection
    test_eval.py             # Parametrized pytest entry point
    report.py                # Results aggregation + console/markdown output + auto-named report files
```

### conftest.py

The eval fixture builds a real `AgentLoop` with the actual ChromaDB and real LLM calls. Same wiring pattern as `gradio_app._get_agent_loop()`:

```python
@pytest.fixture(scope="session")
def agent_loop():
    """Real AgentLoop with real ChromaDB and real LLM calls."""
    planner_llm   = llm_client_for(settings.planner_model)
    rewriter_llm  = llm_client_for(settings.query_rewriter_model)
    evaluator_llm = llm_client_for(settings.evaluator_model)
    synthesis_llm = llm_client_for(settings.synthesis_model)

    return AgentLoop(
        planner=Planner(planner_llm, QueryRewriter(rewriter_llm)),
        evaluator=Evaluator(evaluator_llm),
        hybrid_search=HybridSearch(Retriever()),
        llm_client=synthesis_llm,
    )

@pytest.fixture(scope="session")
def eval_judge():
    """LLM-as-judge client."""
    return EvalJudge(llm_client_for(settings.eval_judge_model))
```

### test_eval.py

```python
@pytest.mark.eval
@pytest.mark.parametrize("case", GOLDEN_CASES, ids=lambda c: c.id)
def test_eval(case: EvalCase, agent_loop, eval_judge):
    result = run_or_cached(case, agent_loop)

    # Layer 1: Action routing (hard assert)
    assert result.planner_output.action == case.expected_action, (
        f"Expected action={case.expected_action}, got={result.planner_output.action}"
    )

    # Layer 2: Filters (hard assert, conditional)
    if case.expected_filters and result.planner_output.action == "search":
        filter_results = check_filters(case.expected_filters, result.planner_output.search_plan.filters)
        for field_name, passed in filter_results.items():
            assert passed, f"Filter mismatch on {field_name}"

    # Layer 3: Strategy (hard assert, conditional)
    if case.expected_response_strategy and result.planner_output.action == "respond":
        assert result.planner_output.response_strategy == case.expected_response_strategy

    # Layer 4-5: Judge scores (collect, do NOT assert)
    if result.final_response:
        scores = eval_judge.score(case, result)
        # Store scores for aggregate reporting (via pytest plugin or fixture)
```

### pytest Configuration

Add to `pyproject.toml`:

```toml
[tool.pytest.ini_options]
markers = ["eval: LLM evaluation tests (hit real APIs, cost money)"]
```

The existing `addopts` should exclude eval markers from default runs. Evals must be explicitly triggered:

```bash
# Run all evals
uv run pytest -m eval -v

# Run only deterministic checks (still hits LLMs for pipeline, but no judge calls)
uv run pytest -m eval -k "not judge" -v

# Default test run — evals excluded
uv run pytest tests/
```

---

## Reporting

### Console Output

After an eval run, `report.py` produces a summary:

```
═══ ChatShop Eval Report ═══

Models:
  planner:      gpt-4o-mini
  rewriter:     gpt-4o-mini
  evaluator:    gpt-4o-mini
  synthesis:    gpt-4o-mini
  judge:        gpt-4o-mini

Action Routing:    24/25 (96.0%)
  clear_search:    8/8
  clarify:         5/5
  informational:   3/3
  off_topic:       3/3
  edge_case:       2/3  [FAIL: edge_02 expected=search got=respond]
  multi_turn:      3/3

Filter Extraction: 7/8 (87.5%)
  [FAIL: search_05 — system set max_price=50 but expected None]

Response Strategy: 6/6 (100.0%)

Judge Scores (avg):        Ground  Help  Person  Constr  Overall
  clear_search (8):          4.5   4.2    4.4     4.3     4.4
  edge_case (3):             3.8   3.5    4.1     3.2     3.9
  multi_turn (3):            4.2   4.0    4.3     4.0     4.1
  OVERALL:                   4.3   4.0    4.3     4.0     4.2

Pipeline Stats (25 cases):
  Avg cost/turn:     $0.012
  Avg latency/turn:  1.8s
```

### Per-Case Detail

For failed or low-scoring cases, include:

- Query and conversation history
- Expected vs actual action/filters/strategy
- Judge scores with reasons
- Full assistant response text

This makes debugging straightforward — you can see exactly where the pipeline diverged.

### Markdown Output

Reports are saved to `tests/evals/results/` with auto-generated names encoding the model config and timestamp:

```
tests/evals/results/eval_gpt4o-mini_2026-03-19_143022.md
tests/evals/results/eval_gpt4o_2026-03-19_150511.md
```

Naming convention: `eval_{primary_model}_{date}_{time}.md`

The primary model is the planner model (the most impactful component). If multiple components use different models, the report header lists all of them — the filename is just for quick identification.

This enables git-tracked history and side-by-side comparison of eval runs across different model configurations.

---

## Cost and Latency Tracking

### Data Source: Langfuse

Cost and latency data is pulled from Langfuse traces (Phase 3), not tracked in application code. This avoids duplicating instrumentation — Langfuse already captures per-generation token counts, cost, and latency for every LLM call.

The eval runner queries Langfuse after each pipeline run to collect:

- **Per-generation cost** — token count x model pricing, computed by Langfuse
- **Per-generation latency** — wall-clock time for each LLM call
- **Per-trace totals** — sum across all generations in one agent turn

This data is aggregated in the eval report as pipeline-level stats.

Requirement: Langfuse must be configured (env vars set) for cost/latency to appear in reports. If Langfuse is not configured, cost/latency fields show "N/A" and the eval still runs — quality metrics do not depend on observability.

### Langfuse Integration in Runner

The runner uses the Langfuse Python SDK to fetch trace data after each eval case completes:

1. Each eval case runs through `AgentLoop.run_with_result()`, which creates a Langfuse trace (via existing Phase 3 instrumentation)
2. After the pipeline completes, the runner calls `langfuse.fetch_trace(trace_id)` to get the full trace with generations
3. Cost and latency are extracted from the trace's generation observations
4. Results are stored alongside the `AgentResult` in the cache

### What Gets Tracked

| Metric | Source | Granularity |
|--------|--------|-------------|
| Token count (input/output) | Langfuse generation observations | Per LLM call |
| Cost ($) | Langfuse cost calculation (model pricing) | Per LLM call, aggregated per case |
| Latency (ms) | Langfuse generation `end_time - start_time` | Per LLM call, aggregated per case |

The report shows **per-turn averages** (cost and latency) for the pipeline only — judge LLM calls are excluded. This gives a realistic picture of what one agent turn costs and how fast it responds, which is the number that matters for production.

---

## Model Comparison Workflow

The eval system supports comparing different model configurations by running evals multiple times with different `.env` settings and comparing the saved reports.

### Workflow

1. Configure models in `.env`:
   ```env
   PLANNER_MODEL=gpt-4o-mini
   QUERY_REWRITER_MODEL=gpt-4o-mini
   EVALUATOR_MODEL=gpt-4o-mini
   SYNTHESIS_MODEL=gpt-4o-mini
   ```

2. Run evals:
   ```bash
   uv run pytest -m eval -v
   ```

3. Report auto-saved to `tests/evals/results/eval_gpt4o-mini_2026-03-19_143022.md`

4. Change models in `.env`:
   ```env
   PLANNER_MODEL=gpt-4o
   QUERY_REWRITER_MODEL=gpt-4o-mini
   EVALUATOR_MODEL=gpt-4o-mini
   SYNTHESIS_MODEL=gpt-4o
   ```

5. Clear cache and re-run:
   ```bash
   EVAL_REFRESH=1 uv run pytest -m eval -v
   ```

6. Compare reports side by side:
   ```bash
   diff tests/evals/results/eval_gpt4o-mini_2026-03-19_143022.md \
        tests/evals/results/eval_gpt4o_2026-03-19_150511.md
   ```

### What You Learn From Comparison

Each saved report contains the full model config + accuracy + cost + latency, enabling trade-off analysis:

```
                    gpt-4o-mini     gpt-4o
Action Routing:     96%             100%
Filter Extraction:  88%             94%
Judge Avg:          4.2             4.5
Avg cost/turn:      $0.012          $0.067
Avg latency/turn:   1.8s            3.2s
```

This answers the real question: is the accuracy improvement worth the cost increase?

### Design Note: Why Not Auto-Run Multiple Configs?

Running all model combinations in one command would be a combinatorial explosion (4 components x N models). The manual swap-and-run approach is simpler, cheaper (you only test configs you care about), and produces cleaner reports. Each run is self-contained and independently cacheable.

---

## Production Code Changes

Minimal changes to existing code:

| File | Change | Lines |
|------|--------|-------|
| `src/chatshop/agent/agent_loop.py` | Add `AgentResult` dataclass + `run_with_result()` method | ~25 |
| `src/chatshop/config.py` | Add `eval_judge_model: str = "gpt-4o-mini"` | 1 |
| `pyproject.toml` | Add `eval` pytest marker | 1 |

Everything else is new files under `tests/evals/`.

---

## Files to Reuse (not modify)

| File | What to reuse |
|------|---------------|
| `src/chatshop/agent/planner.py` | `SearchFilters`, `SearchPlan`, `PlannerOutput` union types — deterministic checks compare against these |
| `src/chatshop/agent/evaluator.py` | `EvaluatorOutput` dataclass, `_EvaluatorSchema` Pydantic pattern — judge follows same pattern |
| `src/chatshop/infra/llm_client.py` | `LLMClient`, `llm_client_for()` — judge reuses existing LLM infrastructure |
| `src/chatshop/infra/observability.py` | Langfuse wrapper — runner uses this to fetch trace data for cost/latency metrics |
| `src/chatshop/ui/gradio_app.py` | `_get_agent_loop()` wiring — conftest fixture mirrors this pattern |
| `src/chatshop/data/models.py` | `Product` model — for test fixtures and result serialization |

---

## Implementation Order

1. `tests/evals/golden_dataset.py` + `__init__.py` — define `EvalCase` schema, write first 5 cases
2. `AgentResult` + `run_with_result()` in `agent_loop.py` — expose structured pipeline output
3. `tests/evals/conftest.py` — real AgentLoop fixture
4. `tests/evals/metrics.py` — deterministic comparison functions
5. `tests/evals/runner.py` — pipeline execution wrapper + caching
6. `tests/evals/judge.py` — LLM-as-judge with Pydantic schema
7. `tests/evals/test_eval.py` — parametrized pytest entry point
8. `tests/evals/report.py` — aggregation + console output
9. Fill remaining ~20 golden dataset cases
10. `pyproject.toml` + `config.py` — marker + judge model setting

---

## Verification

1. `uv run pytest tests/` — existing tests still pass (evals excluded by default)
2. `uv run pytest -m eval -v` — runs all 25 eval cases against real pipeline
3. Action routing accuracy target: >90%
4. Judge scores populated and reasonable (>3.0 avg across all dimensions)
5. `EVAL_REFRESH=1 uv run pytest -m eval` — cache refresh works
6. Console report renders correctly with per-category breakdowns

---

## Design Decisions

### Why Python file for golden dataset, not JSON?

Type checking, IDE autocomplete, inline comments per case, and `field(default_factory=...)` for history lists. JSON would be more portable but less ergonomic for 25 cases with nested structures.

### Why separate deterministic and judge layers?

Action routing should be 100% reliable — that is a real regression. LLM judge scores are inherently noisy (same prompt, same model, different day = different score). Mixing these into a single pass/fail would create flaky tests. Deterministic checks are hard asserts. Judge scores are aggregated metrics.

### Why cache pipeline outputs?

The expensive part is running 25 queries through the full pipeline (~100 LLM calls). Caching means you can iterate on judge prompts or deterministic check logic without re-running the pipeline. Cache invalidation is manual (env var) rather than automatic — eval datasets change infrequently.

### Why `@pytest.mark.eval` instead of a separate script?

pytest gives fixtures, markers, parametrize, and existing CI integration for free. The marker keeps evals out of the normal test run while preserving the standard workflow developers already know.

### Why gpt-4o-mini as default judge model?

Good enough for structured scoring at low cost. The judge only needs to assess quality on a 1-5 scale with a reason, not generate creative responses. Can be upgraded to gpt-4o or claude-sonnet if judge quality is insufficient.

### Why pull cost/latency from Langfuse instead of tracking in LLMClient?

Langfuse already captures per-generation token counts, cost, and latency as part of Phase 3 observability. Duplicating this in LLMClient would add complexity with no additional signal. The eval runner simply reads what Langfuse already records. If Langfuse is not configured, cost/latency show as "N/A" — quality metrics still work.

### Why not auto-run multiple model configs?

4 components x N model options = combinatorial explosion. The manual swap-and-run approach tests only configs you actually care about, produces cleaner reports, and each run is independently cacheable. The auto-named report files make comparison trivial.
