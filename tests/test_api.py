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

    # Получение первого вопроса
    response = client.post(f"/aeon/question/{token}", json={})
    assert response.status_code == 200
    question_data = response.json()
    question_id = question_data["question_id"]

    # Сохранение ответа для этого вопроса
    answer = {"question_id": question_id, "answer": "Мой ответ на первый вопрос"}
    response = client.post(f"/session/{token}/answer", json=answer)
    assert response.status_code == 200
    assert response.json()["status"] == "saved"

    # Получение состояния сессии
    response = client.get(f"/session/{token}")
    assert response.status_code == 200
    data = response.json()
    assert data["questions_answered"] == 1
    assert data["asked_questions"] == 1

def test_stats():
    # Создаём сессию и сохраняем ответ для статистики
    response = client.post("/session")
    token = response.json()["token"]
    
    # Получаем вопрос
    response = client.post(f"/aeon/question/{token}", json={})
    question_id = response.json()["question_id"]
    
    # Отвечаем на вопрос
    client.post(f"/session/{token}/answer", json={"question_id": question_id, "answer": "Тестовый ответ"})

    response = client.get("/stats")
    assert response.status_code == 200
    data = response.json()
    assert data["sessions"] >= 1
    assert data["answers"] >= 1
    assert "avg_score" in data

def test_generate_glyph(monkeypatch):
    # Создаём сессию и добавляем качественные ответы
    response = client.post("/session")
    token = response.json()["token"]
    
    # Получаем несколько вопросов и отвечаем на них
    for i in range(3):
        response = client.post(f"/aeon/question/{token}", json={})
        if response.status_code == 200:
            question_data = response.json()
            question_id = question_data["question_id"]
            
            # Качественный ответ с примерами и ключевыми словами
            good_answer = f"Это детальный ответ на вопрос {i+1}. Например, в моем опыте работы я использовал различные технологии и навыки для решения сложных проблем. Конкретно, я работал с командой над проектами, которые требовали аналитического мышления и профессионального подхода."
            
            client.post(f"/session/{token}/answer", json={"question_id": question_id, "answer": good_answer})
    
    # Генерируем глиф
    response = client.post(f"/aeon/glyph/{token}", json={})
    assert response.status_code == 200
    data = response.json()
    assert "glyph" in data
    assert "profile" in data
    assert "Детали анализа" in data["profile"]

def test_no_question_repetition():
    """Тест на отсутствие повторяющихся вопросов"""
    # Создаём сессию
    response = client.post("/session")
    token = response.json()["token"]
    
    asked_questions = set()
    
    # Запрашиваем все 10 вопросов
    for i in range(10):
        response = client.post(f"/aeon/question/{token}", json={})
        if response.status_code == 200:
            question_data = response.json()
            question_id = question_data["question_id"]
            
            # Проверяем, что вопрос не повторяется
            assert question_id not in asked_questions, f"Вопрос {question_id} повторился!"
            asked_questions.add(question_id)
            
            # Отвечаем на вопрос
            client.post(f"/session/{token}/answer", json={"question_id": question_id, "answer": f"Ответ на {question_id}"})
    
    # Попытка получить 11-й вопрос должна вернуть 404
    response = client.post(f"/aeon/question/{token}", json={})
    assert response.status_code == 404
    assert "Все вопросы заданы" in response.json()["detail"]

def test_answer_validation():
    """Тест валидации ответов - нельзя отвечать на незаданные вопросы"""
    # Создаём сессию
    response = client.post("/session")
    token = response.json()["token"]
    
    # Попытка ответить на незаданный вопрос
    response = client.post(f"/session/{token}/answer", json={"question_id": "q_999", "answer": "Нелегальный ответ"})
    assert response.status_code == 400
    assert "Вопрос не был задан" in response.json()["detail"]

def test_improved_summary_quality():
    """Тест улучшенного качества сводки"""
    # Создаём сессию
    response = client.post("/session")
    token = response.json()["token"]
    
    # Получаем и отвечаем на несколько вопросов
    for i in range(5):
        response = client.post(f"/aeon/question/{token}", json={})
        if response.status_code == 200:
            question_data = response.json()
            question_id = question_data["question_id"]
            
            # Создаём ответы разного качества
            if i < 2:
                # Качественные ответы
                answer = f"Это подробный и содержательный ответ на вопрос {i+1}. Например, в моем профессиональном опыте я сталкивался с множеством технических вызовов, которые требовали аналитического подхода. Конкретно, я работал в команде над проектами, где применял современные технологии для решения бизнес-задач."
            else:
                # Базовые ответы
                answer = f"Краткий ответ {i+1}"
            
            client.post(f"/session/{token}/answer", json={"question_id": question_id, "answer": answer})
    
    # Получаем сводку
    response = client.post(f"/aeon/summary/{token}")
    assert response.status_code == 200
    summary_data = response.json()
    
    # Проверяем, что сводка содержит детальный анализ
    summary = summary_data["summary"]
    assert "Подробный анализ интервью" in summary
    assert "Общая статистика" in summary
    assert "Анализ качества ответов" in summary
    assert "Профессиональная оценка" in summary
    assert "Рекомендации для следующих этапов" in summary
    assert "Итоговый балл:" in summary

def test_performance_score_calculation():
    """Тест расчета итогового балла производительности"""
    # Создаём сессию
    response = client.post("/session")
    token = response.json()["token"]
    
    # Получаем состояние сессии (должно быть 0 баллов)
    response = client.get(f"/session/{token}")
    assert response.json()["current_performance"] == 0
    
    # Отвечаем на вопрос качественно
    response = client.post(f"/aeon/question/{token}", json={})
    question_data = response.json()
    question_id = question_data["question_id"]
    
    # Качественный ответ
    quality_answer = "Это исчерпывающий ответ, который демонстрирует мои профессиональные навыки и опыт работы. Например, в предыдущих проектах я успешно применял аналитическое мышление для решения сложных технических задач. Конкретно, я разрабатывал архитектуру системы, которая повысила производительность на 40%."
    
    client.post(f"/session/{token}/answer", json={"question_id": question_id, "answer": quality_answer})
    
    # Проверяем обновленный балл
    response = client.get(f"/session/{token}")
    performance_score = response.json()["current_performance"]
    assert performance_score > 0, "Балл должен быть больше 0 после качественного ответа"

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
    sessions[token].created_at -= timedelta(hours=2)

    # Любой запрос с истёкшим токеном — 403
    r = client.post(f"/session/{token}/answer", json={"question_id": 1, "answer": "test"})
    assert r.status_code == 403
    assert "истёк" in r.json()["detail"]

    # Создаём новую сессию
    response = client.post("/session")
    token2 = response.json()["token"]
    # Завершаем сессию
    r = client.post(f"/session/{token2}/complete")
    assert r.status_code == 200
    # Повторное прохождение запрещено
    r = client.post(f"/session/{token2}/answer", json={"question_id": 1, "answer": "test"})
    assert r.status_code == 403
    assert "завершён" in r.json()["detail"]

def test_answer_quality_analysis():
    """Тест анализа качества ответов"""
    from app.api import analyze_answer_quality
    
    # Тест качественного ответа
    quality_answer = "Это подробный ответ с примерами и конкретными навыками. Например, я использовал Python для разработки веб-приложений. Конкретно, я работал с FastAPI и создавал REST API."
    keywords = ["навыки", "опыт", "технологии", "разработка"]
    
    result = analyze_answer_quality(quality_answer, keywords)
    
    assert result["score"] > 50, "Качественный ответ должен иметь высокий балл"
    assert result["word_count"] > 20, "Должно быть достаточно слов"
    assert result["has_examples"] is True, "Должны быть обнаружены примеры"
    
    # Тест некачественного ответа
    poor_answer = "Да"
    result = analyze_answer_quality(poor_answer, keywords)
    
    assert result["score"] <= 20, "Некачественный ответ должен иметь низкий балл"
    assert result["word_count"] < 5, "Должно быть мало слов"
    assert result["has_examples"] is False, "Не должно быть примеров"

def test_multiple_sessions_isolation():
    """Тест изоляции между сессиями"""
    # Создаём две сессии
    response1 = client.post("/session")
    token1 = response1.json()["token"]
    
    response2 = client.post("/session")
    token2 = response2.json()["token"]
    
    # Получаем вопросы в обеих сессиях
    response1 = client.post(f"/aeon/question/{token1}", json={})
    q1_data = response1.json()
    
    response2 = client.post(f"/aeon/question/{token2}", json={})
    q2_data = response2.json()
    
    # Отвечаем только в первой сессии
    client.post(f"/session/{token1}/answer", json={"question_id": q1_data["question_id"], "answer": "Ответ в первой сессии"})
    
    # Проверяем состояние сессий
    response1 = client.get(f"/session/{token1}")
    response2 = client.get(f"/session/{token2}")
    
    assert response1.json()["questions_answered"] == 1
    assert response2.json()["questions_answered"] == 0
    assert response1.json()["asked_questions"] == 1
    assert response2.json()["asked_questions"] == 1  # Вопрос был задан, но не отвечен