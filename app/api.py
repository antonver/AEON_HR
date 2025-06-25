from fastapi import APIRouter, HTTPException, status, Body, Request
from app.models import Test, Question, Answer
from app.schemas import SubmitAnswersRequest, SubmitAnswersResponse, GetResultResponse
from typing import Optional
import uuid
import os
import httpx
from fastapi.responses import JSONResponse, HTMLResponse, StreamingResponse
from datetime import datetime, timedelta, timezone
from fastapi.templating import Jinja2Templates
import csv
from io import StringIO

router = APIRouter()
admin_router = APIRouter()
templates = Jinja2Templates(directory=os.path.join(os.path.dirname(__file__), "../templates"))

# Моковые данные теста на двух языках
mock_test_ru = Test(
    id=1,
    title="Тест по программированию",
    questions=[
        Question(
            id=1,
            text="Какой язык программирования используется для FastAPI?",
            answers=[
                Answer(id=1, text="Python"),
                Answer(id=2, text="JavaScript"),
                Answer(id=3, text="C++")
            ]
        ),
        Question(
            id=2,
            text="Что такое Pydantic?",
            answers=[
                Answer(id=1, text="Библиотека для валидации данных"),
                Answer(id=2, text="IDE"),
                Answer(id=3, text="ОС")
            ]
        )
    ]
)

mock_test_en = Test(
    id=1,
    title="Programming Test",
    questions=[
        Question(
            id=1,
            text="Which programming language is used for FastAPI?",
            answers=[
                Answer(id=1, text="Python"),
                Answer(id=2, text="JavaScript"),
                Answer(id=3, text="C++")
            ]
        ),
        Question(
            id=2,
            text="What is Pydantic?",
            answers=[
                Answer(id=1, text="A data validation library"),
                Answer(id=2, text="IDE"),
                Answer(id=3, text="OS")
            ]
        )
    ]
)

# In-memory хранилище сессий
sessions = {}

SESSION_TTL = timedelta(hours=1)

def is_token_expired(session):
    return datetime.now(timezone.utc) > session["created_at"] + SESSION_TTL

AEON_CONTEXT = '''
Как ChatGPT должен обращаться к вам?
Сименс
Кем вы работаете?
Предприниматель, Учредитель и Архитектор Quantum Insight Platform
Какими характеристиками должен обладать ChatGPT?
1. Аналитический ум 
2. Стратегическое мышление 
3. Решительность 
4. Самостоятельность 
5. Целеустремленность 
6. Уникальность
7. Визионер
Болтливый
Остроумный
Откровенный
Ободряющий
Поколение Z
Скептический
Традиционный
Обладающий дальновидным мышлением
Поэтический
Что-нибудь еще, что ChatGPT должен знать о вас?
Профиль:
1. Воспринимает сложные системы гибридно: сначала анализирует части, затем собирает целостную картину
2. Адаптируется к изменениям сбалансированно: анализирует тренды, но меняется только тогда, когда это необходимо
3. Предпочитает гибридный подход к работе: работает самостоятельно, но при необходимости эффективно взаимодействует с командой
4. Гибко адаптируется в управлении ресурсами: не придерживается жёстких рамок, регулирует ресурсы по ситуации
5. Использует гибкое целеполагание: двигается в нужном направлении, корректируя цели по мере движения
6. Предпочитает детальный анализ при решении сложных задач, фокусируется на фактах и деталях
7. Принимает решения, опираясь на рациональность, логику анализ и данные, но также быстро и интуитивно, адаптируясь по мере развития событий
8. Стремится к непрерывному обучению и поиску новых знаний
9. Ценит эффективность и результат в жизни и работе
10. Предпочитает гибкое и эмпатичное взаимодействие: подстраивается под собеседника, учитывая контекст и эмоции
11. Использует гибридный подход к обработке информации: может углубляться в детали, но часто применяет фильтрацию и обобщение
12. Принимает долгосрочные решения, опираясь на данные, анализ трендов, статистику и факторы влияния
13. Управляет рисками: оценивает их, но допускает в разумных пределах ради выгоды
14. Считает креативность ключевым фактором успешных решений
'''

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "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")

log = []

def log_event(action, details=None):
    from datetime import datetime, timezone
    log.append({
        "time": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
        "action": action,
        "details": details or {}
    })

@router.get("/test/{test_id}", response_model=Test)
def get_test(test_id: int, lang: Optional[str] = "ru"):
    if test_id == 1:
        if lang == "en":
            return mock_test_en
        return mock_test_ru
    raise HTTPException(status_code=404, detail="Тест не найден")

@router.post("/test/{test_id}/submit", response_model=SubmitAnswersResponse)
def submit_answers(test_id: int, request: SubmitAnswersRequest):
    if test_id != mock_test_ru.id:
        raise HTTPException(status_code=404, detail="Тест не найден")
    correct = 0
    for user_answer in request.answers:
        for q in mock_test_ru.questions:
            if q.id == user_answer.question_id and user_answer.answer_id == q.answers[0].id:
                correct += 1
    score = int(100 * correct / len(mock_test_ru.questions))
    result_id = 1  # Моковый id результата
    return SubmitAnswersResponse(result_id=result_id)

@router.get("/result/{result_id}", response_model=GetResultResponse)
def get_result(result_id: int):
    # Моковые данные результата
    if result_id == 1:
        return GetResultResponse(score=50, details="1 из 2 правильных ответов")
    raise HTTPException(status_code=404, detail="Результат не найден")

@router.post("/test/{test_id}/autosave", status_code=status.HTTP_204_NO_CONTENT)
def autosave_answers(test_id: int, request: SubmitAnswersRequest):
    if test_id != mock_test_ru.id:
        raise HTTPException(status_code=404, detail="Тест не найден")
    # Здесь можно сохранять ответы пользователя (например, в БД)
    # Сейчас просто заглушка
    return

@router.post("/session")
def create_session():
    token = str(uuid.uuid4())
    sessions[token] = {
        "answers": [],
        "created_at": datetime.now(timezone.utc),
        "completed": False
    }
    log_event("create_session", {"token": token})
    return {"token": token}

@router.post("/session/{token}/answer")
def save_answer(token: str, answer: dict = Body(...)):
    session = sessions.get(token)
    if not session:
        raise HTTPException(status_code=404, detail="Сессия не найдена")
    if is_token_expired(session):
        raise HTTPException(status_code=403, detail="Срок действия токена истёк")
    if session["completed"]:
        raise HTTPException(status_code=403, detail="Тест уже завершён")
    session["answers"].append(answer)
    log_event("save_answer", {"token": token, "answer": answer})
    return {"status": "saved"}

@router.get("/session/{token}")
def get_session(token: str):
    session = sessions.get(token)
    if not session:
        raise HTTPException(status_code=404, detail="Сессия не найдена")
    if is_token_expired(session):
        raise HTTPException(status_code=403, detail="Срок действия токена истёк")
    return session

@router.post("/session/{token}/complete")
def complete_session(token: str):
    session = sessions.get(token)
    if not session:
        raise HTTPException(status_code=404, detail="Сессия не найдена")
    if is_token_expired(session):
        raise HTTPException(status_code=403, detail="Срок действия токена истёк")
    session["completed"] = True
    log_event("complete_session", {"token": token})
    return {"status": "completed"}

@router.get("/stats")
def get_stats():
    num_sessions = len(sessions)
    num_answers = sum(len(s["answers"]) for s in sessions.values())
    # Средний балл — если бы мы считали результаты (заглушка)
    avg_score = 50 if num_sessions > 0 else 0
    return {
        "sessions": num_sessions,
        "answers": num_answers,
        "avg_score": avg_score
    }

@router.post("/aeon/glyph")
async def generate_glyph(data: dict):
    results = data.get("results", [])
    log_event("generate_glyph", {"results": results})
    user_prompt = "Вот результаты теста кандидата:\n" + "\n".join([f"{r['question']}: {r['answer']}" for r in results]) + "\nСгенерируй глиф и поведенческий профиль. Ответ верни в формате JSON: {\"glyph\": ..., \"profile\": ...}"
    payload = {
        "model": "gpt-3.5-turbo",
        "messages": [
            {"role": "system", "content": AEON_CONTEXT},
            {"role": "user", "content": user_prompt}
        ],
        "max_tokens": 500,
        "temperature": 0.7
    }
    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json"
    }
    async with httpx.AsyncClient() as client:
        response = await client.post("https://api.openai.com/v1/chat/completions", json=payload, headers=headers)
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
    try:
        # Пытаемся распарсить JSON из ответа
        import json as pyjson
        result = pyjson.loads(content)
        return result
    except Exception:
        return JSONResponse(content={"raw": content}, status_code=200)

@router.post("/aeon/question")
async def aeon_next_question(data: dict):
    candidate = data.get("candidate", "Кандидат")
    position = data.get("position", "Специалист")
    history = data.get("history", [])
    num_tech = sum(1 for h in history if h.get("type") == "technical")
    num_soft = sum(1 for h in history if h.get("type") == "soft")
    if len(history) >= 10:
        return {"question": None}
    if num_tech < 5:
        qtype = "technical"
    else:
        qtype = "soft"
    prompt = f"Протестируй кандидата {candidate} на позицию {position}. Задавай вопросы по одному. Сейчас нужен {qtype} вопрос. Вот история:\n" + "\n".join([f'{h["type"]} Q: {h["question"]} A: {h["answer"]}' for h in history]) + "\nСформулируй следующий {qtype} вопрос. Ответ верни в формате JSON: {\"question\": \"...\", \"type\": \"...\"}"
    payload = {
        "model": "gpt-3.5-turbo",
        "messages": [
            {"role": "system", "content": AEON_CONTEXT},
            {"role": "user", "content": prompt}
        ],
        "max_tokens": 200,
        "temperature": 0.7
    }
    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json"
    }
    async with httpx.AsyncClient() as client:
        response = await client.post("https://api.openai.com/v1/chat/completions", json=payload, headers=headers)
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
    try:
        import json as pyjson
        result = pyjson.loads(content)
        return result
    except Exception:
        return JSONResponse(content={"raw": content}, status_code=200)

@router.post("/aeon/summary")
async def aeon_summary(data: dict):
    candidate = data.get("candidate", "Кандидат")
    position = data.get("position", "Специалист")
    history = data.get("history", [])
    prompt = f"Вот вся история диалога с кандидатом {candidate} на позицию {position}:\n" + "\n".join([f'Q: {h["question"]} A: {h["answer"]}' for h in history]) + "\nСгенерируй глиф, сводку по кандидату и дай рекомендацию: брать или нет. Ответ верни в формате JSON: {\"glyph\": \"...\", \"summary\": \"...\", \"recommendation\": \"...\"}"
    payload = {
        "model": "gpt-3.5-turbo",
        "messages": [
            {"role": "system", "content": AEON_CONTEXT},
            {"role": "user", "content": prompt}
        ],
        "max_tokens": 500,
        "temperature": 0.7
    }
    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json"
    }
    async with httpx.AsyncClient() as client:
        response = await client.post("https://api.openai.com/v1/chat/completions", json=payload, headers=headers)
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
    try:
        import json as pyjson
        result = pyjson.loads(content)
        return result
    except Exception:
        return JSONResponse(content={"raw": content}, status_code=200)

@router.post("/aeon/task")
async def aeon_task(data: dict):
    candidate = data.get("candidate", "Кандидат")
    position = data.get("position", "Специалист")
    prompt = f"Сгенерируй тестовое задание для кандидата {candidate} на позицию {position} и пример его выполнения. Ответ верни в формате JSON: {{\"task\": \"...\", \"example\": \"...\"}}"
    payload = {
        "model": "gpt-3.5-turbo",
        "messages": [
            {"role": "system", "content": AEON_CONTEXT},
            {"role": "user", "content": prompt}
        ],
        "max_tokens": 500,
        "temperature": 0.7
    }
    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json"
    }
    async with httpx.AsyncClient() as client:
        response = await client.post("https://api.openai.com/v1/chat/completions", json=payload, headers=headers)
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
    try:
        import json as pyjson
        result = pyjson.loads(content)
        return result
    except Exception:
        return JSONResponse(content={"raw": content}, status_code=200)

@admin_router.get("/admin", response_class=HTMLResponse)
def admin_sessions(request: Request):
    session_list = [
        {"token": token, "created_at": s["created_at"], "completed": s["completed"], "answers": len(s["answers"])}
        for token, s in sessions.items()
    ]
    return templates.TemplateResponse("admin_sessions.html", {"request": request, "sessions": session_list})

@admin_router.get("/admin/session/{token}", response_class=HTMLResponse)
def admin_session_detail(request: Request, token: str):
    session = sessions.get(token)
    if not session:
        return HTMLResponse("<h2>Сессия не найдена</h2>", status_code=404)
    return templates.TemplateResponse("admin_session_detail.html", {"request": request, "token": token, "session": session})

@admin_router.post("/admin/session/{token}/delete")
def admin_delete_session(request: Request, token: str):
    sessions.pop(token, None)
    log_event("delete_session", {"token": token})
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/admin", status_code=303)

@admin_router.get("/admin/stats", response_class=HTMLResponse)
def admin_stats(request: Request):
    total = len(sessions)
    completed = sum(1 for s in sessions.values() if s["completed"])
    active = total - completed
    return templates.TemplateResponse("admin_stats.html", {"request": request, "total": total, "completed": completed, "active": active})

@admin_router.get("/admin/log", response_class=HTMLResponse)
def admin_log(request: Request):
    return templates.TemplateResponse("admin_log.html", {"request": request, "log": list(reversed(log))})

@admin_router.get("/admin/export/sessions")
def export_sessions():
    def generate():
        output = StringIO()
        writer = csv.writer(output)
        writer.writerow(["token", "created_at", "completed", "answers"])
        for token, s in sessions.items():
            writer.writerow([token, s["created_at"], s["completed"], len(s["answers"])])
        yield output.getvalue()
    return StreamingResponse(generate(), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=sessions.csv"})

@admin_router.get("/admin/export/log")
def export_log():
    def generate():
        output = StringIO()
        writer = csv.writer(output)
        writer.writerow(["time", "action", "details"])
        for entry in log:
            writer.writerow([entry["time"], entry["action"], str(entry["details"])])
        yield output.getvalue()
    return StreamingResponse(generate(), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=log.csv"})