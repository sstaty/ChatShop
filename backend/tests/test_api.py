from fastapi.testclient import TestClient

from chatshop.api.sse_events import DoneEvent, ResponseChunkEvent
from main import app


class _StubLoop:
    def __init__(self, events=None, error: Exception | None = None) -> None:
        self._events = events or []
        self._error = error

    def stream_with_trace(self, message: str, history: list, shown_products=None):
        if self._error is not None:
            raise self._error
        yield from self._events


def test_chat_stream_returns_sse_chunks(monkeypatch):
    events = [
        ResponseChunkEvent(text="ANC "),
        ResponseChunkEvent(text="reduces noise."),
        DoneEvent(),
    ]
    monkeypatch.setattr("main.get_agent_loop", lambda: _StubLoop(events=events))

    client = TestClient(app)
    response = client.post(
        "/chat/stream",
        json={"message": "What is ANC?", "history": [], "shown_products": []},
    )

    assert response.status_code == 200
    assert "ANC " in response.text
    assert "reduces noise." in response.text


def test_chat_stream_returns_error_event_on_failure(monkeypatch):
    monkeypatch.setattr(
        "main.get_agent_loop",
        lambda: _StubLoop(error=RuntimeError("backend exploded")),
    )

    client = TestClient(app)
    response = client.post(
        "/chat/stream",
        json={"message": "Hi", "history": []},
    )

    assert response.status_code == 200
    assert "Stream failed" in response.text
