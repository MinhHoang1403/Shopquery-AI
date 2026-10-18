"""FastAPI contract tests independent of Gemini and PostgreSQL."""

from fastapi.testclient import TestClient

from app.core.errors import ModelResponseError
from app.main import app
from app.routing.router import RouteLabel
from app.routing.service import ChatResult


class FakeChatService:
    def chat(self, question: str) -> ChatResult:
        return ChatResult("Có 10 đơn hoàn thành.", RouteLabel.SQL, "SELECT 10", [{"total": 10}])


class FailingChatService:
    def chat(self, question: str) -> ChatResult:
        raise ModelResponseError("Gemini generation remained unavailable after retry attempts")


def test_health_does_not_require_gemini() -> None:
    response = TestClient(app).get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "ShopQuery AI"}


def test_chat_has_consistent_response(monkeypatch) -> None:
    monkeypatch.setattr("app.api.routes.build_chat_service", lambda settings: FakeChatService())
    response = TestClient(app).post("/api/chat", json={"message": "Bao nhiêu đơn?"})
    assert response.status_code == 200
    assert response.json() == {
        "answer": "Có 10 đơn hoàn thành.",
        "route": "SQL",
        "sql": "SELECT 10",
        "rows": [{"total": 10}],
        "sources": [],
        "error": None,
        "requested_model": None,
        "used_model": None,
        "fallback_used": False,
        "fallback_reason": None,
    }


def test_chat_rejects_blank_and_oversized_input() -> None:
    client = TestClient(app)
    assert client.post("/api/chat", json={"message": "   "}).status_code == 422
    assert client.post("/api/chat", json={"message": "x" * 2_001}).status_code == 422


def test_chat_does_not_fabricate_response_when_generation_fails(monkeypatch) -> None:
    monkeypatch.setattr("app.api.routes.build_chat_service", lambda settings: FailingChatService())

    response = TestClient(app).post("/api/chat", json={"message": "Top sản phẩm?"})

    assert response.status_code == 200
    assert response.json() == {
        "answer": "Không thể hoàn tất câu hỏi bằng dữ liệu hiện có.",
        "route": None,
        "sql": None,
        "rows": [],
        "sources": [],
        "error": "Gemini generation remained unavailable after retry attempts",
        "requested_model": "inetcloud-knowledge",
        "used_model": None,
        "fallback_used": False,
        "fallback_reason": None,
    }
