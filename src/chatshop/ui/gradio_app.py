from collections.abc import Generator

import gradio as gr

from chatshop.rag.chain import RAGChain

_chain: RAGChain | None = None


def _get_chain() -> RAGChain:
    global _chain
    if _chain is None:
        _chain = RAGChain()
    return _chain


def respond(
    message: str,
    history: list[dict],
) -> Generator[tuple[list[dict], str, str], None, None]:
    """Streaming handler — yields (history, retrieval_info, input_clear)."""
    chain = _get_chain()
    info, stream = chain.retrieve_and_stream(message, history)

    history = history + [{"role": "user", "content": message}]
    yield history, info, ""

    partial = ""
    for token in stream:
        partial += token
        yield history + [{"role": "assistant", "content": partial}], info, ""

    history = history + [{"role": "assistant", "content": partial}]


def build_app() -> gr.Blocks:
    with gr.Blocks(title="ChatShop") as demo:
        gr.Markdown(
            "## ChatShop\n"
            "Describe what you're looking for and I'll find the best matching products."
        )

        with gr.Row():
            with gr.Column(scale=3):
                chatbot = gr.Chatbot(height=500)
                msg_input = gr.Textbox(
                    placeholder="Ask about a product…",
                    show_label=False,
                    lines=1,
                )
                with gr.Row():
                    send_btn = gr.Button("Send", variant="primary")
                    clear_btn = gr.Button("Clear")

            with gr.Column(scale=1):
                sidebar = gr.Textbox(
                    label="Retrieval Reasoning",
                    interactive=False,
                    lines=20,
                )

        outputs = [chatbot, sidebar, msg_input]

        msg_input.submit(respond, inputs=[msg_input, chatbot], outputs=outputs)
        send_btn.click(respond, inputs=[msg_input, chatbot], outputs=outputs)
        clear_btn.click(
            lambda: ([], "", ""),
            outputs=[chatbot, sidebar, msg_input],
        )

    return demo


def launch(**kwargs) -> None:
    app = build_app()
    app.launch(theme=gr.themes.Soft(), **kwargs)
