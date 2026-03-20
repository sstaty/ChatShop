"""
LLM-as-judge for ChatShop evals (layers 4-5).

JudgeScores — Pydantic model for structured LLM output (follows the same
              _EvaluatorSchema pattern used elsewhere in the codebase).
EvalJudge   — Scores a pipeline result on 4 dimensions using an LLM.

Judge scores are NEVER used as pass/fail assertions — they are aggregated
and reported as quality metrics.
"""

from __future__ import annotations

import json

from pydantic import BaseModel, ConfigDict

from chatshop.agent.agent_loop import AgentResult
from chatshop.infra.llm_client import LLMClient

from tests.evals.golden_dataset import EvalCase


# ---------------------------------------------------------------------------
# Scoring schema
# ---------------------------------------------------------------------------


class JudgeScores(BaseModel):
    """Structured output from the LLM judge. All scores are 1–5."""

    model_config = ConfigDict(extra="forbid")

    groundedness: int
    groundedness_reason: str
    helpfulness: int
    helpfulness_reason: str
    personality: int
    personality_reason: str
    constraint_adherence: int
    constraint_adherence_reason: str

    def overall(self) -> float:
        """Average across applicable dimensions (excludes -1 N/A values)."""
        scores = [
            s for s in [
                self.groundedness, self.helpfulness,
                self.personality, self.constraint_adherence,
            ]
            if s >= 0
        ]
        return sum(scores) / len(scores) if scores else 0.0


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

_FULL_RUBRIC = """\
Score each dimension 1–5 using these rubrics:

Groundedness (1–5):
  5 = Every product mentioned is from the retrieved set. All specs/prices accurate.
  4 = Products from retrieved set. Minor details paraphrased but not fabricated.
  3 = Products from retrieved set but some specs slightly off or embellished.
  2 = Most products exist but some details clearly fabricated.
  1 = Hallucinated products or invented specifications.

Helpfulness (1–5):
  5 = Directly addresses intent, actionable recommendation with clear reasoning.
  4 = Addresses intent with useful recommendation; reasoning could be stronger.
  3 = Addresses intent but lacks specificity or reasoning.
  2 = Partially relevant but misses key aspects of the request.
  1 = Generic response that could apply to any query.

Personality (1–5):
  5 = Sounds like ChatShop — witty, knowledgeable friend, not a product manual.
  4 = Warm and engaging with some character.
  3 = Professional but bland.
  2 = Overly formal or robotic.
  1 = Reads like a database dump.

Constraint Adherence (1–5):
  5 = Respects all user constraints (budget, features, type). Explains impossible constraints clearly.
  4 = Respects most constraints; minor deviations explained.
  3 = Partially addresses constraints, misses one.
  2 = Ignores some stated constraints.
  1 = Recommends products violating stated constraints without acknowledgment."""

_CLARIFY_RUBRIC = """\
Score each dimension 1–5 (groundedness and constraint_adherence are not applicable \
for clarify cases — set them to 0):

Helpfulness (1–5):
  5 = Clarifying question targets the right missing information and efficiently narrows the search.
  4 = Targets the right information; slightly verbose or misses a secondary constraint.
  3 = Asks a question but it's vague or covers too much ground at once.
  2 = Asks about something that won't help much, or misses the core missing info.
  1 = Question is irrelevant or unhelpful.

Personality (1–5):
  5 = Warm, conversational, feels like asking a knowledgeable friend.
  4 = Friendly with some character.
  3 = Neutral and polite but bland.
  2 = Formal or interrogative.
  1 = Cold or robotic."""


def _build_prompt(case: EvalCase, result: AgentResult) -> list[dict]:
    """Build the judge prompt messages for a given case and pipeline result."""
    history_text = ""
    if case.history:
        lines = []
        for msg in case.history:
            role = msg["role"].capitalize()
            lines.append(f"{role}: {msg['content']}")
        history_text = "\n".join(lines)

    products_text = "No products retrieved."
    if result.search_results:
        products_text = "\n\n".join(p.to_context_text() for p in result.search_results)

    rubric = _CLARIFY_RUBRIC if case.expected_action == "clarify" else _FULL_RUBRIC

    user_content = f"""\
You are evaluating a headphone shopping assistant's response.

## User Query
{case.query}

## Conversation History
{history_text or "None"}

## User's Intent
{case.intent_description}

## Retrieved Products (what the system had available)
{products_text}

## Assistant Response
{result.final_response}

## Quality Notes
{case.quality_notes}

{rubric}

Respond with JSON only — no commentary outside the JSON object."""

    return [{"role": "user", "content": user_content}]


# ---------------------------------------------------------------------------
# EvalJudge
# ---------------------------------------------------------------------------


class EvalJudge:
    """Scores a pipeline result using an LLM judge."""

    def __init__(self, llm_client: LLMClient) -> None:
        self._llm = llm_client

    def score(self, case: EvalCase, result: AgentResult) -> JudgeScores:
        """Score *result* on all four dimensions.

        For clarify cases, groundedness and constraint_adherence are set to 0
        (not applicable). Helpfulness and personality are scored normally.

        Returns:
            A :class:`JudgeScores` instance with 1–5 scores and reasons.
        """
        messages = _build_prompt(case, result)
        raw = self._llm.complete(messages, response_format=JudgeScores)
        data = json.loads(raw)

        # For clarify cases, override non-applicable dimensions with -1 sentinel
        if case.expected_action == "clarify":
            data["groundedness"] = -1
            data["groundedness_reason"] = "N/A — clarify case"
            data["constraint_adherence"] = -1
            data["constraint_adherence_reason"] = "N/A — clarify case"

        return JudgeScores(**data)
