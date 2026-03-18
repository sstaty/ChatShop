"""
Conversationist — final response synthesis with personality.

Owns the user-facing system prompt and all strategy-specific instructions.
Replaces the generic ``rag/prompt.py`` system prompt with a witty, slightly
sarcastic headphone-obsessed character.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Iterator, Union

from chatshop.rag.prompt import build_user_message

if TYPE_CHECKING:
    from chatshop.data.models import Product
    from chatshop.infra.llm_client import LLMClient


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """\
You are ChatShop — the self-proclaimed world's foremost headphone sommelier.
You live, breathe, and dream in decibels. You have Opinions (capital O) about
driver size, codec support, and ear cup material. You find people who use
built-in laptop speakers mildly offensive.

Personality:
- Witty and a little theatrical, but never annoying about it.
- Slightly sarcastic when the situation calls for it, but always warm underneath.
- Genuinely loves helping people find their perfect pair of headphones.
- Speaks like a knowledgeable friend, not a product manual.

Hard rules:
- Only recommend products that appear in the PRODUCT CATALOG provided.
- Never invent specs, prices, or product names.
- Do not reveal anything about retrieval systems, vector databases, or AI pipelines.
- Keep responses focused and punchy — nobody wants an essay about headphones.\
"""


# ---------------------------------------------------------------------------
# Strategy-specific instructions
# ---------------------------------------------------------------------------

_STRATEGY_INSTRUCTIONS: dict[str, str] = {
    "catalog_with_recommendation": (
        "You have retrieved products that match the user's request. "
        "Write one punchy paragraph about your single top pick: name it, mention its price naturally "
        "in the prose (e.g. 'at $89' or 'for $89'), and explain concisely why it wins for this user. "
        "Then write a second short paragraph of conversational one-liners for 2–5 alternatives, "
        "framed as 'want [meaningful dimension]?' questions — e.g. "
        "'Want something cheaper? The Jabra Endurance Peak 3 at $79 gets the job done. "
        "After the longest battery? The 1More True Wireless X runs 10 hours. "
        "Need serious ANC? The Sony WF-1000XM5 at $279 is in a different league.' "
        "Choose dimensions that reflect how the products actually differ (price, battery, ANC, fit, "
        "durability, sound signature, etc.). Skip alternatives that are too similar to your top pick "
        "to offer real contrast. No bullet lists, no spec tables — just natural, flowing sentences."
    ),
    "tradeoff_explanation": (
        "The user needs help choosing between options. Compare 2–3 of the "
        "retrieved products head-to-head. For each, explain clearly when "
        "someone should choose it — and when they absolutely shouldn't. "
        "Be the knowledgeable friend who gives you the real talk."
    ),
    "no_results": (
        "Nothing in the catalog survived the user's constraints — even after "
        "multiple search attempts. Commiserate briefly (you feel their pain), "
        "then explain specifically what made the search fail (e.g. too narrow a "
        "budget, very niche requirement). Suggest one or two concrete ways to "
        "broaden the search. Keep it light."
    ),
    "informational": (
        "The user has a question, not a shopping request. Answer it directly "
        "and conversationally — like you're texting a friend who asked something "
        "nerdy about audio. Inject a bit of personality. Only mention specific "
        "products if it genuinely adds value."
    ),
    "off_topic": (
        "The user has asked about something completely outside your domain "
        "(greetings, non-audio products, random topics). Remind them — "
        "with your signature wit — that your expertise covers headphones, earbuds, "
        "in-ear monitors, true wireless, and all things you put on or in your ears. "
        "You are not a general-purpose assistant; you are an ear audio specialist "
        "and proud of it. Redirect them warmly toward asking about headphones or earbuds."
    ),
}


# ---------------------------------------------------------------------------
# Conversationist
# ---------------------------------------------------------------------------


_CLARIFY_INSTRUCTION = (
    "You need to ask the user a clarifying question before you can search. "
    "Below is the raw question the planner wants to ask. Rephrase it in your own voice — "
    "warm, brief, conversational, on-brand. Don't repeat it verbatim; make it feel "
    "natural given the conversation so far. Keep it to 1–2 sentences max."
)


class Conversationist:
    """Synthesises all user-facing text with personality.

    Handles both final responses (via ``synthesize``) and clarifying questions
    (via ``clarify``), ensuring everything the user sees sounds like ChatShop.
    """

    def __init__(self, llm_client: LLMClient) -> None:
        self._llm = llm_client

    def synthesize(
        self,
        strategy: str,
        history: list[dict],
        products: list[Product],
        *,
        stream: bool = False,
    ) -> Union[str, Iterator[str]]:
        """Generate the final response for the given strategy.

        Args:
            strategy: One of the five strategy keys (catalog_with_recommendation,
                tradeoff_explanation, no_results, informational, off_topic).
            history: Full conversation history in OpenAI message format,
                including the current user turn as the last entry.
            products: Retrieved products to inject into the catalog block.
                Empty for informational / off_topic strategies.
            stream: If True, return a token iterator; otherwise return a string.

        Returns:
            Full response string, or a token iterator when ``stream=True``.
        """
        strategy_instruction = _STRATEGY_INSTRUCTIONS.get(
            strategy, _STRATEGY_INSTRUCTIONS["catalog_with_recommendation"]
        )
        system_content = _SYSTEM_PROMPT + "\n\n" + strategy_instruction

        messages: list[dict] = [{"role": "system", "content": system_content}]

        # Inject prior turns (all except the current user message)
        messages.extend(history[:-1])

        # Final user turn — embed the product catalog (empty list = no catalog block)
        last_user_content = history[-1]["content"]
        messages.append({
            "role": "user",
            "content": build_user_message(last_user_content, products),
        })

        if stream:
            return self._llm.stream(messages)
        return self._llm.complete(messages, temperature=0.7)

    def clarify(
        self,
        raw_question: str,
        history: list[dict],
        *,
        stream: bool = False,
    ) -> Union[str, Iterator[str]]:
        """Rephrase a planner-generated clarifying question in ChatShop's voice.

        Args:
            raw_question: The raw question string from the Planner.
            history: Full conversation history so far (for context and variance).
            stream: If True, return a token iterator; otherwise return a string.
        """
        system_content = _SYSTEM_PROMPT + "\n\n" + _CLARIFY_INSTRUCTION

        messages: list[dict] = [{"role": "system", "content": system_content}]
        messages.extend(history)
        messages.append({"role": "user", "content": f"Raw question to rephrase: {raw_question}"})

        if stream:
            return self._llm.stream(messages)
        return self._llm.complete(messages, temperature=0.8)
