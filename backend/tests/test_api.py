from fastapi.testclient import TestClient

from chatshop.agent.agent_loop import AgentResult
from chatshop.agent.evaluator import EvaluatorOutput
from chatshop.agent.planner import RespondAction
from main import app


class _StubLoop:
    def __init__(self, result: AgentResult | None = None, error: Exception | None = None) -> None:
        self._result = result
        self._error = error

    def run_with_result(self, message: str, history: list[dict]) -> AgentResult:
        if self._error is not None:
            raise self._error
        assert self._result is not None
        return self._result


def test_chat_returns_agent_result(monkeypatch):
    result = AgentResult(
        planner_output=RespondAction(
            action="respond",
            response_strategy="informational",
            reasoning_trace="User asked an informational question.",
        ),
        search_results=None,
        evaluator_output=EvaluatorOutput(
            diagnosis="sufficient",
            blocking_constraints=[],
            reason="No retrieval needed.",
        ),
        final_response="ANC reduces external noise.",
        iterations=0,
        trace_id=None,
    )

    monkeypatch.setattr("main.get_agent_loop", lambda: _StubLoop(result=result))

    client = TestClient(app)
    response = client.post("/chat", json={"message": "What is ANC?", "history": []})

    assert response.status_code == 200
    assert response.json() == {
        "response": "ANC reduces external noise.",
        "reasoning_trace": "Planner: User asked an informational question.\nEvaluator: sufficient\nReason: No retrieval needed.",
    }


def test_chat_returns_500_when_agent_loop_fails(monkeypatch):
    monkeypatch.setattr(
        "main.get_agent_loop",
        lambda: _StubLoop(error=RuntimeError("backend exploded")),
    )

    client = TestClient(app)
    response = client.post("/chat", json={"message": "Hi", "history": []})

    assert response.status_code == 500
    assert response.json() == {"detail": "backend exploded"}