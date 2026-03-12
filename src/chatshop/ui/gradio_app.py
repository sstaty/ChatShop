import gradio as gr

from chatshop.rag.chain import RAGChain

_chain: RAGChain | None = None


def _get_chain() -> RAGChain:
    global _chain
    if _chain is None:
        _chain = RAGChain()
    return _chain


def _chat_handler(
    message: str,
    history: list[dict],
) -> gr.render:
    """Streaming chat handler for Gradio Blocks."""
    chain = _get_chain()
    partial = ""
    for token in chain.stream(message):
        partial += token
        yield partial


def build_app() -> gr.Blocks:
    with gr.Blocks(title="ChatShop", theme=gr.themes.Soft()) as demo:
        gr.Markdown(
            "## ChatShop\n"
            "Describe what you're looking for and I'll find the best matching products."
        )
        gr.ChatInterface(
            fn=_chat_handler,
            type="messages",
            examples=[
                "wireless headphones under $100",
                "best laptop for machine learning under $1500",
                "noise cancelling earbuds with long battery life",
                "mechanical keyboard for programming",
            ],
            cache_examples=False,
        )
    return demo


def launch(**kwargs) -> None:
    app = build_app()
    app.launch(**kwargs)
