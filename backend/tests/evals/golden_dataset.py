"""
Golden dataset for ChatShop end-to-end evals.

25 cases covering: clear search (8), clarify (5), informational (3),
off-topic (3), edge cases (3), multi-turn (3).

expected_filters mirrors SearchFilters structure:
  {"max_price": ..., "min_price": ..., "extra_filters": {...}}
Only include fields you want to assert — missing keys are not checked.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


@dataclass
class EvalCase:
    # Identity
    id: str
    category: str
    description: str

    # Input
    query: str
    history: list[dict] = field(default_factory=list)

    # Deterministic expectations
    expected_action: Literal["clarify", "search", "respond"] = "search"
    expected_filters: dict | None = None   # mirrors SearchFilters; None for non-search cases
    expected_response_strategy: str | None = None  # only for respond cases

    # LLM-as-judge context
    intent_description: str = ""
    quality_notes: str = ""


# ---------------------------------------------------------------------------
# Clear Search Cases (8)
# ---------------------------------------------------------------------------

GOLDEN_CASES: list[EvalCase] = [
    EvalCase(
        id="search_01",
        category="clear_search",
        description="Wireless earbuds with price cap and use-case hint",
        query="wireless earbuds for running under $80",
        expected_action="search",
        expected_filters={
            "max_price": 80.0,
            "extra_filters": {"wireless": True},
        },
        intent_description="User wants wireless earbuds suitable for running, with a hard budget of $80.",
        quality_notes=(
            "Response should recommend earbuds that are wireless and priced under $80. "
            "Bonus if it highlights sport/sweat resistance. Should not recommend wired or over-budget options."
        ),
    ),
    EvalCase(
        id="search_02",
        category="clear_search",
        description="ANC headphones under $200",
        query="best noise cancelling headphones under $200",
        expected_action="search",
        expected_filters={
            "max_price": 200.0,
            "extra_filters": {"anc": True},
        },
        intent_description="User wants headphones with active noise cancellation under $200.",
        quality_notes=(
            "Response should feature ANC headphones priced at or below $200. "
            "Should explain ANC quality differences if multiple options are shown."
        ),
    ),
    EvalCase(
        id="search_03",
        category="clear_search",
        description="Wired over-ear headphones (no price constraint)",
        query="wired over-ear headphones",
        expected_action="search",
        expected_filters={
            "extra_filters": {"wireless": False, "type": "over-ear"},
        },
        intent_description="User explicitly wants wired (not wireless) over-ear headphones. No budget constraint stated.",
        quality_notes=(
            "All recommended products must be wired and over-ear. "
            "Should not suggest wireless options or in-ear products."
        ),
    ),
    EvalCase(
        id="search_04",
        category="clear_search",
        description="Open-back headphones for audio mixing",
        query="open-back headphones for mixing",
        expected_action="search",
        expected_filters={
            "extra_filters": {"type": "open-back"},
        },
        intent_description="User is an audio professional looking for open-back headphones for mixing/studio use.",
        quality_notes=(
            "Should recommend open-back headphones. "
            "Ideal response mentions why open-back suits mixing (soundstage, accurate imaging). "
            "Should not infer a price filter."
        ),
    ),
    EvalCase(
        id="search_05",
        category="clear_search",
        description="Cheap bluetooth earbuds — 'cheap' should not become a price filter",
        query="cheap bluetooth earbuds",
        expected_action="search",
        expected_filters={
            "extra_filters": {"wireless": True},
        },
        intent_description="User wants budget-friendly wireless earbuds. 'Cheap' is subjective and should not be translated to a specific price filter.",
        quality_notes=(
            "Should recommend wireless earbuds, preferably toward the lower price range. "
            "Should NOT set a hard price cap from the word 'cheap' alone."
        ),
    ),
    EvalCase(
        id="search_06",
        category="clear_search",
        description="Top-rated wireless earbuds under $150",
        query="top-rated wireless earbuds under $150",
        expected_action="search",
        expected_filters={
            "max_price": 150.0,
            "extra_filters": {"wireless": True},
        },
        intent_description="User wants the best-reviewed wireless earbuds within a $150 budget.",
        quality_notes=(
            "Should recommend wireless earbuds under $150. "
            "Response should highlight quality/value. Should not exceed budget."
        ),
    ),
    EvalCase(
        id="search_07",
        category="clear_search",
        description="Earbuds with battery life constraint",
        query="earbuds with at least 8 hours battery",
        expected_action="search",
        expected_filters={
            "extra_filters": {"min_battery_hours": 8},
        },
        intent_description="User needs earbuds with a minimum of 8 hours battery life.",
        quality_notes=(
            "Should recommend earbuds with at least 8 hours battery. "
            "Good response mentions battery specs for each option."
        ),
    ),
    EvalCase(
        id="search_08",
        category="clear_search",
        description="ANC headphones in a price range ($100-$250)",
        query="ANC headphones between $100 and $250",
        expected_action="search",
        expected_filters={
            "min_price": 100.0,
            "max_price": 250.0,
            "extra_filters": {"anc": True},
        },
        intent_description="User wants ANC headphones with both a floor and ceiling on price.",
        quality_notes=(
            "Should recommend headphones with ANC priced between $100 and $250 inclusive. "
            "Should respect both the minimum and maximum price bounds."
        ),
    ),

    # ---------------------------------------------------------------------------
    # Clarify Cases (5)
    # ---------------------------------------------------------------------------

    EvalCase(
        id="clarify_01",
        category="clarify",
        description="Gym use case — no budget, no type",
        query="I need something for the gym",
        expected_action="clarify",
        expected_filters=None,
        expected_response_strategy=None,
        intent_description="User wants audio gear for gym/workout use but has given no budget or form factor preference.",
        quality_notes=(
            "Should ask about budget and/or earbuds vs headphones preference. "
            "Should be warm and concise, not a multi-question interrogation."
        ),
    ),
    EvalCase(
        id="clarify_02",
        category="clarify",
        description="Generic earbuds request — no context",
        query="I need new earbuds",
        expected_action="clarify",
        expected_filters=None,
        expected_response_strategy=None,
        intent_description="User wants earbuds but has given no use case or budget information.",
        quality_notes=(
            "Should ask about budget and/or use case. "
            "Tone should be friendly and helpful, not robotic."
        ),
    ),
    EvalCase(
        id="clarify_03",
        category="clarify",
        description="Gift query — headphones for daughter, no constraints",
        query="headphones for my daughter",
        expected_action="clarify",
        expected_filters=None,
        expected_response_strategy=None,
        intent_description="User is buying a gift with no stated budget, age/use case, or type preference.",
        quality_notes=(
            "Should ask about budget and what the daughter will use them for. "
            "Tone should be helpful and conversational."
        ),
    ),
    EvalCase(
        id="clarify_04",
        category="clarify",
        description="Commuting use case — ambiguous form factor",
        query="something for commuting",
        expected_action="clarify",
        expected_filters=None,
        expected_response_strategy=None,
        intent_description="User wants audio gear for commuting but hasn't said budget or earbuds vs headphones.",
        quality_notes=(
            "Should ask about budget and preference between earbuds and over-ear. "
            "Commuting could imply ANC preference — mentioning this in the question is a bonus."
        ),
    ),
    EvalCase(
        id="clarify_05",
        category="clarify",
        description="Completely generic headphone request",
        query="I'm looking for a good pair of headphones",
        expected_action="clarify",
        expected_filters=None,
        expected_response_strategy=None,
        intent_description="Maximally generic query with no constraints — budget, type, and use case all absent.",
        quality_notes=(
            "Should ask about budget and use case or type preference. "
            "Should not search without any constraints."
        ),
    ),

    # ---------------------------------------------------------------------------
    # Informational Cases (3)
    # ---------------------------------------------------------------------------

    EvalCase(
        id="info_01",
        category="informational",
        description="What is ANC?",
        query="what is ANC?",
        expected_action="respond",
        expected_filters=None,
        expected_response_strategy="informational",
        intent_description="User wants an explanation of what active noise cancellation is.",
        quality_notes=(
            "Should explain ANC clearly and concisely. "
            "Good response mentions how it works (microphones + inverse sound wave). "
            "Should not recommend products unless it flows naturally."
        ),
    ),
    EvalCase(
        id="info_02",
        category="informational",
        description="Open-back vs closed-back difference",
        query="what's the difference between open-back and closed-back?",
        expected_action="respond",
        expected_filters=None,
        expected_response_strategy="informational",
        intent_description="User wants to understand the trade-offs between open-back and closed-back headphone designs.",
        quality_notes=(
            "Should explain both types clearly: open-back = soundstage/leakage, closed-back = isolation/bass. "
            "Should mention use cases for each. "
            "Conversational and engaging tone preferred."
        ),
    ),
    EvalCase(
        id="info_03",
        category="informational",
        description="DAC for wireless headphones question",
        query="do I need a DAC for wireless headphones?",
        expected_action="respond",
        expected_filters=None,
        expected_response_strategy="informational",
        intent_description="User is confused about whether wireless headphones require an external DAC.",
        quality_notes=(
            "Should clarify that wireless headphones have built-in DAC/amp, so no external DAC needed. "
            "Good response briefly explains why (analog signal conversion happens in the headphone). "
            "Should not be condescending."
        ),
    ),

    # ---------------------------------------------------------------------------
    # Off-Topic Cases (3)
    # ---------------------------------------------------------------------------

    EvalCase(
        id="offtopic_01",
        category="off_topic",
        description="Greeting with no product intent",
        query="hey",
        expected_action="respond",
        expected_filters=None,
        expected_response_strategy="off_topic",
        intent_description="User sent a greeting. No shopping intent expressed.",
        quality_notes=(
            "Should greet warmly and invite the user to ask about headphones/earbuds. "
            "Should be brief and conversational, not a long welcome speech."
        ),
    ),
    EvalCase(
        id="offtopic_02",
        category="off_topic",
        description="Laptop recommendation request (non-audio product)",
        query="can you recommend a good laptop?",
        expected_action="respond",
        expected_filters=None,
        expected_response_strategy="off_topic",
        intent_description="User is asking for a laptop recommendation, which is outside the scope of this audio-focused assistant.",
        quality_notes=(
            "Should politely decline and redirect to headphones/earbuds. "
            "Tone should be friendly, not dismissive."
        ),
    ),
    EvalCase(
        id="offtopic_03",
        category="off_topic",
        description="Weather question (completely unrelated)",
        query="what's the weather like?",
        expected_action="respond",
        expected_filters=None,
        expected_response_strategy="off_topic",
        intent_description="User asked about the weather, which is completely unrelated to audio shopping.",
        quality_notes=(
            "Should acknowledge it can't help with weather and steer back to audio. "
            "Brief and light-hearted response preferred."
        ),
    ),

    # ---------------------------------------------------------------------------
    # Edge Cases (3)
    # ---------------------------------------------------------------------------

    EvalCase(
        id="edge_01",
        category="edge_case",
        description="Extremely tight budget ($20) for best sound quality",
        query="best sound quality under $20",
        expected_action="search",
        expected_filters={
            "max_price": 20.0,
        },
        expected_response_strategy=None,  # may be no_results or narrow_results — not asserted
        intent_description="User wants maximum audio quality within a $20 budget — a very tight constraint.",
        quality_notes=(
            "Should acknowledge the tight budget and set realistic expectations. "
            "If products exist, present them honestly. If not, explain why and suggest a realistic budget."
        ),
    ),
    EvalCase(
        id="edge_02",
        category="edge_case",
        description="Contradictory: wireless ANC open-back (almost doesn't exist)",
        query="wireless ANC open-back headphones",
        expected_action="search",
        expected_filters={
            "extra_filters": {"wireless": True, "anc": True, "type": "open-back"},
        },
        expected_response_strategy=None,  # may be no_results, narrow_results, or tradeoff_explanation
        intent_description="User wants all three features: wireless, ANC, and open-back design — a nearly impossible combination.",
        quality_notes=(
            "Should attempt to find matching products. If none exist, should explain the contradiction: "
            "ANC is fundamentally incompatible with open-back design. "
            "Should suggest alternatives (closed-back ANC wireless, or open-back wired)."
        ),
    ),
    EvalCase(
        id="edge_03",
        category="edge_case",
        description="Waterproof over-ear for swimming (nearly impossible)",
        query="waterproof over-ear headphones for swimming",
        expected_action="search",
        expected_filters={
            "extra_filters": {"type": "over-ear"},
        },
        expected_response_strategy=None,  # likely no_results or narrow_results
        intent_description="User wants over-ear headphones rated for submersion (swimming). Essentially no consumer products meet this spec.",
        quality_notes=(
            "Should try to find waterproof over-ear options. "
            "If none found, should explain why swimming-grade waterproofing is rare for over-ear headphones "
            "and suggest bone conduction or sport earbuds as alternatives."
        ),
    ),

    # ---------------------------------------------------------------------------
    # Multi-Turn Cases (3)
    # ---------------------------------------------------------------------------

    EvalCase(
        id="multi_01",
        category="multi_turn",
        description="User answers budget question from prior clarification",
        query="under $100",
        history=[
            {"role": "user", "content": "headphones for commuting"},
            {
                "role": "assistant",
                "content": (
                    "Happy to help! To point you toward the right options — "
                    "what's your budget, and do you prefer earbuds or over-ear headphones?"
                ),
            },
        ],
        expected_action="search",
        expected_filters={
            "max_price": 100.0,
        },
        intent_description=(
            "After being asked for budget and type, the user only provided a budget ($100). "
            "The system should search with the budget constraint and infer commuting context."
        ),
        quality_notes=(
            "Should search and return relevant results under $100. "
            "ANC would be a natural fit for commuting — good response might highlight this."
        ),
    ),
    EvalCase(
        id="multi_02",
        category="multi_turn",
        description="Follow-up question about battery after seeing search results",
        query="which has the longest battery?",
        history=[
            {"role": "user", "content": "wireless earbuds under $100"},
            {
                "role": "assistant",
                "content": (
                    "Here are some solid picks under $100:\n\n"
                    "1. SoundCore Liberty 4 NC — $80, 10h battery, ANC\n"
                    "2. JLab Go Air Pop — $25, 8h battery, lightweight\n"
                    "3. Jabra Elite 4 — $99, 6h battery, ANC\n\n"
                    "My top pick is the SoundCore Liberty 4 NC for the ANC + battery combo."
                ),
            },
        ],
        expected_action="respond",
        expected_filters=None,
        expected_response_strategy="tradeoff_explanation",
        intent_description="User is comparing products shown in previous turn and wants to know which has the best battery life.",
        quality_notes=(
            "Should compare battery life across the products shown. "
            "Should not retrieve new products — answer from the existing context. "
            "Good response is direct: clearly states which has longest battery and by how much."
        ),
    ),
    EvalCase(
        id="multi_03",
        category="multi_turn",
        description="Search refinement — adds 'good for calls' constraint to prior wireless earbuds search",
        query="only ones good for calls",
        history=[
            {"role": "user", "content": "wireless earbuds under $80"},
            {
                "role": "assistant",
                "content": (
                    "Great options under $80:\n\n"
                    "1. SoundCore Life P3 — $60, wireless, good ANC\n"
                    "2. JLab Go Air Sport — $50, sport-fit, basic mic\n"
                    "3. Edifier TWS1 Pro 2 — $70, warm sound\n\n"
                    "The SoundCore Life P3 is my pick for all-around value."
                ),
            },
        ],
        expected_action="search",
        expected_filters={
            "max_price": 80.0,
            "extra_filters": {"wireless": True},
        },
        intent_description=(
            "User wants to refine the prior search to only include earbuds good for phone calls. "
            "The $80 budget and wireless constraint from the first turn should carry over."
        ),
        quality_notes=(
            "Should search for wireless earbuds under $80 with good microphone/call quality. "
            "Should not ignore the original budget constraint. "
            "Response should explain which are best suited for calls."
        ),
    ),
]
