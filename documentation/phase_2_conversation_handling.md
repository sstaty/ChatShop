# Conversational Constraint Handling

This document defines how ChatShop handles over‑constrained or very narrow user queries in a conversational way.

Design principle:

The system should NOT automatically relax constraints or guess the next‑best alternative.
Instead, it should transparently explain the situation and let the user decide which constraint to adjust.

---

## Responsibility split

Evaluator = diagnostic module
Planner = conversational decision maker

Flow:

search → evaluator diagnosis → planner decides how to respond

Evaluator never talks to the user directly.
Planner builds the conversational response.

---

## Evaluator diagnosis model

Evaluator combines:

1) Deterministic coded signals
2) LLM reasoning

### Deterministic signals (must be coded)

These should NOT rely on an LLM.

- result_count = number of retrieved products

Diagnosis rules:

- result_count == 0 → "no_results"
- result_count in [1,2] → "narrow_results"
- result_count >= 3 → "sufficient_candidate_set"

These signals are always computed in code before calling the LLM.

---

### LLM diagnosis (semantic reasoning)

The LLM evaluator is responsible for identifying:

- which constraints are likely unrealistic
- which constraint most strongly limits feasibility
- whether results violate user intent (e.g. wrong use case)

Example structured output:

{
  "diagnosis": "overconstrained_query",
  "blocking_constraints": ["price"],
  "reason": "No over‑ear office headphones exist under the requested budget"
}

Important: this reasoning depends on both:

- the user intent summary
- the applied search filters
- the retrieved evidence set (or lack of it)

---

## Planner conversational strategies

Based on evaluator diagnosis, the Planner chooses how to proceed.

### Case: No results

Planner response goals:

- clearly explain that no products match
- explain which constraint is likely too strict
- ask user which constraint they want to relax

Example response strategy:

"I couldn't find any over‑ear headphones suitable for office use under $30.\
The closest options start around $45. Would you prefer increasing the budget or changing the form factor?"

---

### Case: Very narrow results (1–2 products)

Planner response goals:

- recommend the available options
- explain that the criteria are very specific
- offer to broaden the search

Example:

"I found only two earbuds that match all your criteria.\
If you'd like more choices, we could relax the waterproof requirement or slightly increase the budget."

---

### Case: Sufficient candidate set

Planner proceeds with normal recommendation synthesis.

---

## Why evaluator cannot be purely coded

Identifying the critical constraint is not always trivial.

Example:

Query: "ANC headphones for running under $50"

Possible blocking factors:

- ANC at low price
- running suitability
- product form factor

Determining the true limiting factor requires semantic reasoning about product capabilities.
Therefore the evaluator uses:

- coded quantitative signals (result_count)
- LLM qualitative reasoning (constraint feasibility)

This hybrid diagnostic approach provides both:

- reliability
- conversational intelligence

---

## Future improvements

Potential enhancements:

- statistical price‑range awareness per product category
- learned constraint feasibility heuristics
- ranking‑based constraint sensitivity analysis
- explicit feasibility prediction before search

These are not required for the initial agentic implementation.

