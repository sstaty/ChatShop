from collections.abc import Generator

import gradio as gr

from chatshop.agent.agent_loop import AgentLoop, TraceEvent
from chatshop.runtime import get_agent_loop


def respond(
    message: str,
    history: list[dict],
) -> Generator[tuple[list[dict], str, str], None, None]:
    """Streaming handler — yields (history, trace_text, input_clear)."""
    loop = get_agent_loop()
    history_with_user = history + [{"role": "user", "content": message}]
    trace_text = ""
    partial = ""

    yield history_with_user, trace_text, ""

    for event in loop.stream_with_trace(message, history):
        if isinstance(event, TraceEvent):
            trace_text += event.text + "\n"
            yield history_with_user, trace_text, ""
        else:
            partial += event
            yield (
                history_with_user + [{"role": "assistant", "content": partial}],
                trace_text,
                "",
            )


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

            with gr.Column(scale=2):
                sidebar = gr.Textbox(
                    label="Agent Reasoning",
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
