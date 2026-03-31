# ChatShop — Eval Model Comparison

## Evaluation Overview

Each model configuration was evaluated against a golden dataset of 25 test cases spanning clarification, search, edge cases, informational, multi-turn, and off-topic queries. The eval system uses **deterministic checks** for structured outputs (action routing, filter extraction, response strategy) and an **LLM-as-judge** (gpt-4o-mini) scoring response quality on groundedness, helpfulness, personality, and constraint adherence (1-5 scale). Cost and latency were pulled from Langfuse traces.

## Model Comparison

Single-model configurations use one model for all agent roles (planner, rewriter, evaluator, synthesis). Mixed configurations use the listed planner model with gpt-4o-mini for all other roles.

| Model(s) | Action Routing | Filter Extraction | Response Strategy | LLM-as-a-Judge, Overall | Avg Cost/loop | Avg Latency/loop |
|---|---|---|---|---|---|---|
| gpt-4o-mini | 68.0% | 100% | 85.7% | 3.7 | 0.034 ¢ | 7.4 s |
| gpt-4o | 84.0% | 100% | 100% | 4.1 | 0.72 ¢ | 9.4 s |
| gpt-5.4-mini | 80.0% | 100% | 100% | 4.1 | 0.25 ¢ | 5.8 s |
| Claude Haiku 4.5 | 96.0% | 83.3% | 100% | 4.3 | 0.344 ¢ | 12.8 s |
| Gemini 3 Flash | 64.0% | 80.0% | 100% | 3.6 | 0.16 ¢ | 7.8 s |
| DeepSeek Chat | 80.0% | 88.9% | 100% | 3.9 | 0.06 ¢ | 20.5 s |
| **gpt-5.4-mini (planner) + gpt-4o-mini** | **80.0%** | **100%** | **100%** | **4.0** | **0.129 ¢** | **7.2 s** |
| Claude Haiku 4.5 (planner) + gpt-4o-mini | 96.0% | 91.7% | 100% | 4.2 | 0.166 ¢ | 12.8 s |

## Winner: gpt-5.4-mini (planner) + gpt-4o-mini

The **gpt-5.4-mini + gpt-4o-mini** combination delivers the best cost-to-quality tradeoff. It scores a solid 4.0 judge overall — matching gpt-4o's quality tier — while costing just 0.129¢ per agent loop (5.6x cheaper than gpt-4o) at only 7.2s latency (the second-fastest configuration tested). Its deterministic scores are clean: 100% on both filter extraction and response strategy, with 80% action routing that's competitive with most single-model setups.

Claude Haiku 4.5 leads on pure quality — 96% routing accuracy and 4.3 judge score — but at roughly 2x the cost and 2x the latency. That premium is hard to justify when the gpt-5.4-mini combo gets you 93% of the quality at a fraction of the price. DeepSeek is the cheapest option at 0.06¢/loop, but its 20.5s latency makes it impractical for a real-time shopping assistant. Gemini 3 Flash scores lowest across the board on quality despite decent speed and cost.

For a production shopping assistant where users expect sub-10s responses and operational cost matters, the mixed gpt-5.4-mini + gpt-4o-mini setup hits the sweet spot. However, it is expected that fine-tuned open source models would be cheaper & perform similarly, but such task was outside of scope for this project
