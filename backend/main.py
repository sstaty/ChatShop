import logging
import sys
from pathlib import Path
from typing import Iterator

sys.path.insert(0, str(Path(__file__).parent / "src"))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

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
    shown_products: list[dict] = []


def _stream_sse(req: ChatRequest) -> Iterator[str]:
    try:
        for event in get_agent_loop().stream_with_trace(
            req.message, req.history, shown_products=req.shown_products or None
        ):
            yield f"data: {event.model_dump_json()}\n\n"
    except Exception:
        logger.exception("Agent stream failed")
        yield f"data: {ErrorEvent(message='Stream failed').model_dump_json()}\n\n"


@app.post("/chat/stream")
def chat_stream(req: ChatRequest):
    return StreamingResponse(_stream_sse(req), media_type="text/event-stream")


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}
