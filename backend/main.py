import logging
from typing import Iterator

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from chatshop.agent.agent_loop import AgentResult
from chatshop.api.sse_events import ErrorEvent
from chatshop.runtime import get_agent_loop

logger = logging.getLogger(__name__)

app = FastAPI(title="ChatShop API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    message: str
    history: list


class ChatResponse(BaseModel):
    response: str
    reasoning_trace: str


def _stream_sse(message: str, history: list) -> Iterator[str]:
    try:
        for event in get_agent_loop().stream_with_trace(message, history):
            yield f"data: {event.model_dump_json()}\n\n"
    except Exception:
        logger.exception("Agent stream failed")
        yield f"data: {ErrorEvent(message='Stream failed').model_dump_json()}\n\n"


def _reasoning_trace_for(result: AgentResult) -> str:
    parts = [f"Planner: {result.planner_output.reasoning_trace}"]

    if result.evaluator_output is not None:
        parts.append(f"Evaluator: {result.evaluator_output.diagnosis}")
        parts.append(f"Reason: {result.evaluator_output.reason}")

    return "\n".join(parts)


@app.post("/chat/stream")
def chat_stream(req: ChatRequest):
    return StreamingResponse(
        _stream_sse(req.message, req.history),
        media_type="text/event-stream",
    )


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    try:
        result = get_agent_loop().run_with_result(req.message, req.history)
    except Exception as exc:
        logger.exception("Agent loop failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return ChatResponse(
        response=result.final_response,
        reasoning_trace=_reasoning_trace_for(result),
    )
