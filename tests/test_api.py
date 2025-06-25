import pytest
from fastapi.testclient import TestClient
from app.main import app
import json
import types
from datetime import timedelta

client = TestClient(app)

def test_get_test():
    response = client.get("/test/1")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == 1
    assert data["title"] == "Тест по программированию"
    assert len(data["questions"]) == 2

def test_submit_answers():
    payload = {
        "answers": [
            {"question_id": 1, "answer_id": 1},  # правильный
            {"question_id": 2, "answer_id": 2}   # неправильный
        ]
    }
    response = client.post("/test/1/submit", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "result_id" in data

def test_get_result():
    response = client.get("/result/1")
    assert response.status_code == 200
    data = response.json()
    assert data["score"] == 50
    assert "правильных" in data["details"]

def test_autosave_answers():
    payload = {
        "answers": [
            {"question_id": 1, "answer_id": 2},
            {"question_id": 2, "answer_id": 3}
        ]
    }
    response = client.post("/test/1/autosave", json=payload)
    assert response.status_code == 204

def test_get_test_ru():
    response = client.get("/test/1?lang=ru")
    assert response.status_code == 200
    data = response.json()
    assert data["title"] == "Тест по программированию"
    assert "язык программирования" in data["questions"][0]["text"]

def test_get_test_en():
    response = client.get("/test/1?lang=en")
    assert response.status_code == 200
    data = response.json()
    assert data["title"] == "Programming Test"
    assert "programming language" in data["questions"][0]["text"]

def test_session_lifecycle():
    # Создание сессии
    response = client.post("/session")
    assert response.status_code == 200
    token = response.json()["token"]

    # Сохранение ответа
    answer = {"question_id": 1, "answer_id": 2}
    response = client.post(f"/session/{token}/answer", json=answer)
    assert response.status_code == 200
    assert response.json()["status"] == "saved"

    # Получение состояния сессии
    response = client.get(f"/session/{token}")
    assert response.status_code == 200
    data = response.json()
    assert data["answers"][0] == answer

def test_stats():
    # Создаём сессию и сохраняем ответ для статистики
    response = client.post("/session")
    token = response.json()["token"]
    client.post(f"/session/{token}/answer", json={"question_id": 1, "answer_id": 2})

    response = client.get("/stats")
    assert response.status_code == 200
    data = response.json()
    assert data["sessions"] >= 1
    assert data["answers"] >= 1
    assert "avg_score" in data

def test_generate_glyph(monkeypatch):
    # Мокаем httpx.AsyncClient.post
    class MockResponse:
        def raise_for_status(self):
            pass
        def json(self):
            return {"choices": [{"message": {"content": json.dumps({"glyph": "🧬", "profile": "Test profile"})}}]}
    class MockAsyncClient:
        async def __aenter__(self):
            return self
        async def __aexit__(self, exc_type, exc, tb):
            pass
        async def post(self, *args, **kwargs):
            return MockResponse()
    monkeypatch.setattr("httpx.AsyncClient", MockAsyncClient)

    payload = {
        "results": [
            {"question": "Вопрос 1", "answer": "Ответ 1"},
            {"question": "Вопрос 2", "answer": "Ответ 2"}
        ]
    }
    response = client.post("/aeon/glyph", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "glyph" in data
    assert "profile" in data

def mock_openai(monkeypatch, content):
    class MockResponse:
        def raise_for_status(self):
            pass
        def json(self):
            return {"choices": [{"message": {"content": content}}]}
    class MockAsyncClient:
        async def __aenter__(self):
            return self
        async def __aexit__(self, exc_type, exc, tb):
            pass
        async def post(self, *args, **kwargs):
            return MockResponse()
    monkeypatch.setattr("httpx.AsyncClient", MockAsyncClient)

def test_aeon_next_question(monkeypatch):
    mock_openai(monkeypatch, '{"question": "Какой ваш любимый язык программирования?", "type": "technical"}')
    payload = {
        "candidate": "Иван Иванов",
        "position": "Backend Developer",
        "history": []
    }
    response = client.post("/aeon/question", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["question"]
    assert data["type"] == "technical"

def test_aeon_summary(monkeypatch):
    mock_openai(monkeypatch, '{"glyph": "🧬", "summary": "Кандидат проявил себя отлично", "recommendation": "Брать"}')
    payload = {
        "candidate": "Иван Иванов",
        "position": "Backend Developer",
        "history": [
            {"question": "Q1", "answer": "A1"},
            {"question": "Q2", "answer": "A2"}
        ]
    }
    response = client.post("/aeon/summary", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "glyph" in data
    assert "summary" in data
    assert "recommendation" in data

def test_aeon_task(monkeypatch):
    mock_openai(monkeypatch, '{"task": "Сделать API", "example": "Пример кода"}')
    payload = {
        "candidate": "Иван Иванов",
        "position": "Backend Developer"
    }
    response = client.post("/aeon/task", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "task" in data
    assert "example" in data

def test_token_expiry_and_reuse():
    # Создаём сессию
    response = client.post("/session")
    token = response.json()["token"]

    # Принудительно истекает срок действия
    from app.api import sessions
    sessions[token]["created_at"] -= timedelta(hours=2)

    # Любой запрос с истёкшим токеном — 403
    r = client.post(f"/session/{token}/answer", json={"question_id": 1, "answer_id": 2})
    assert r.status_code == 403
    assert "истёк" in r.json()["detail"]

    # Создаём новую сессию
    response = client.post("/session")
    token2 = response.json()["token"]
    # Завершаем сессию
    r = client.post(f"/session/{token2}/complete")
    assert r.status_code == 200
    # Повторное прохождение запрещено
    r = client.post(f"/session/{token2}/answer", json={"question_id": 1, "answer_id": 2})
    assert r.status_code == 403
    assert "завершён" in r.json()["detail"]