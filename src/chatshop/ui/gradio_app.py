from collections.abc import Generator

import gradio as gr

from chatshop.agent.agent_loop import AgentLoop, TraceEvent

_agent_loop: AgentLoop | None = None


def _get_agent_loop() -> AgentLoop:
    global _agent_loop
    if _agent_loop is None:
        from chatshop.agent.evaluator import Evaluator
        from chatshop.agent.planner import Planner
        from chatshop.config import settings
        from chatshop.infra.llm_client import llm_client_for
        from chatshop.rag.hybrid_search import HybridSearch
        from chatshop.rag.query_rewriter import QueryRewriter
        from chatshop.rag.retriever import Retriever

        planner_llm   = llm_client_for(settings.planner_model)
        rewriter_llm  = llm_client_for(settings.query_rewriter_model)
        evaluator_llm = llm_client_for(settings.evaluator_model)
        synthesis_llm = llm_client_for(settings.synthesis_model)

        _agent_loop = AgentLoop(
            planner=Planner(planner_llm, QueryRewriter(rewriter_llm)),
            evaluator=Evaluator(evaluator_llm),
            hybrid_search=HybridSearch(Retriever()),
            llm_client=synthesis_llm,
        )
    return _agent_loop


def respond(
    message: str,
    history: list[dict],
) -> Generator[tuple[list[dict], str, str], None, None]:
    """Streaming handler — yields (history, trace_text, input_clear)."""
    loop = _get_agent_loop()
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
