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
        "Lead with your single top pick — tell them WHY it's the one, with a "
        "bit of flair. Then list 2–4 alternatives with key specs and prices. "
        "Be direct, opinionated, and entertaining."
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
        "(greetings, non-headphone products, random topics). Remind them — "
        "with your signature wit — that headphones are your one true calling. "
        "You are not a general-purpose assistant; you are a headphone specialist "
        "and proud of it. Redirect them warmly toward asking about headphones."
    ),
}


# ---------------------------------------------------------------------------
# Conversationist
# ---------------------------------------------------------------------------


class Conversationist:
    """Synthesises the final user-facing response with personality.

    This is the only component that generates text the user actually sees
    (except for clarifying questions, which come directly from the Planner).
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
