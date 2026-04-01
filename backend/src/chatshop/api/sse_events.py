from typing import Any, Literal

from pydantic import BaseModel


class ThinkingEvent(BaseModel):
    type: Literal["thinking"] = "thinking"
    message: str
    detail: str = ""


class IntentEvent(BaseModel):
    type: Literal["intent"] = "intent"
    summary: str
    semantic_query: str
    filters: dict[str, Any]


class ProductsEvent(BaseModel):
    type: Literal["products"] = "products"
    intro: str
    items: list[dict]


class ResponseChunkEvent(BaseModel):
    type: Literal["response_chunk"] = "response_chunk"
    text: str


class ClarifyEvent(BaseModel):
    type: Literal["clarify"] = "clarify"


class DoneEvent(BaseModel):
    type: Literal["done"] = "done"


class ErrorEvent(BaseModel):
    type: Literal["error"] = "error"
    message: str


SSEEvent = (
    ThinkingEvent
    | IntentEvent
    | ProductsEvent
    | ResponseChunkEvent
    | ClarifyEvent
    | DoneEvent
    | ErrorEvent
)
