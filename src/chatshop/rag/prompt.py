from chatshop.data.models import Product

SYSTEM_PROMPT = """\
You are ChatShop, a helpful shopping assistant. Your job is to recommend \
products from the provided catalog that best match what the user is looking for.

Guidelines:
- Only recommend products that appear in the PRODUCT CATALOG below.
- Be concise: lead with your top recommendation, then list alternatives.
- Mention price and rating when available.
- If no product is a good fit, say so honestly — do not hallucinate products.
- Do not reveal that you are using a retrieval system or vector database.\
"""


def build_user_message(query: str, products: list[Product]) -> str:
    """Format retrieved products into a structured context block for the LLM."""
    catalog_lines = ["PRODUCT CATALOG\n" + "=" * 40]
    for i, product in enumerate(products, start=1):
        catalog_lines.append(f"\n[{i}] {product.to_document_text()}")
    catalog_lines.append("\n" + "=" * 40)

    catalog_block = "\n".join(catalog_lines)
    return f"{catalog_block}\n\nUser request: {query}"
