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

# AEON Questions Pool - 10 профессиональных вопросов
AEON_QUESTIONS = [
    {
        "id": "q_1",
        "text": "Расскажите о себе и своем профессиональном опыте. Какие навыки и достижения вы считаете наиболее важными?",
        "type": "technical"
    },
    {
        "id": "q_2", 
        "text": "Опишите свой идеальный рабочий день. Что бы вы делали и как бы себя чувствовали?",
        "type": "soft"
    },
    {
        "id": "q_3",
        "text": "Расскажите о ситуации, когда вам пришлось решать сложную проблему. Как вы подошли к решению?",
        "type": "technical"
    },
    {
        "id": "q_4",
        "text": "Как вы справляетесь со стрессом и давлением на работе? Приведите конкретный пример.",
        "type": "soft"
    },
    {
        "id": "q_5",
        "text": "Расскажите о своем опыте работы в команде. Какую роль вы обычно играете в коллективе?",
        "type": "soft"
    },
    {
        "id": "q_6",
        "text": "Какие технологии, методы или навыки вы изучили за последний год? Что планируете изучить?",
        "type": "technical"
    },
    {
        "id": "q_7",
        "text": "Опишите ситуацию, когда вам пришлось адаптироваться к серьезным изменениям. Как вы это делали?",
        "type": "soft"
    },
    {
        "id": "q_8",
        "text": "Расскажите о своих карьерных целях. Где вы видите себя через 2-3 года?",
        "type": "soft"
    },
    {
        "id": "q_9",
        "text": "Что мотивирует вас в работе больше всего? Что дает вам энергию для профессионального роста?",
        "type": "soft"
    },
    {
        "id": "q_10",
        "text": "Почему вы заинтересованы в работе в нашей компании? Какой вклад вы хотите внести?",
        "type": "soft"
    }
]

# In-memory хранилище сессий (улучшенное)
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
        "aeon_answers": {},  # Новое: ответы AEON
        "asked_questions": set(),  # Новое: заданные вопросы
        "current_question_index": 0,  # Новое: индекс текущего вопроса
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
    
    # Сохраняем обычный ответ
    session["answers"].append(answer)
    
    # Если это AEON ответ, сохраняем отдельно
    if "question_id" in answer:
        session["aeon_answers"][answer["question_id"]] = answer["answer"]
    
    log_event("save_answer", {"token": token, "answer": answer})
    return {"status": "saved"}

@router.get("/session/{token}")
def get_session(token: str):
    session = sessions.get(token)
    if not session:
        raise HTTPException(status_code=404, detail="Сессия не найдена")
    if is_token_expired(session):
        raise HTTPException(status_code=403, detail="Срок действия токена истёк")
    
    # Возвращаем безопасную копию без внутренних данных
    return {
        "token": token,
        "created_at": session["created_at"],
        "completed": session["completed"],
        "questions_answered": len(session["aeon_answers"]),
        "total_questions": len(AEON_QUESTIONS)
    }

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

@router.get("/result/{token}")
def get_result_by_token(token: str):
    session = sessions.get(token)
    if not session:
        raise HTTPException(status_code=404, detail="Сессия не найдена")
    
    total_time = (datetime.now(timezone.utc) - session["created_at"]).total_seconds()
    questions_answered = len(session["aeon_answers"])
    completion_rate = (questions_answered / len(AEON_QUESTIONS)) * 100 if len(AEON_QUESTIONS) > 0 else 0
    
    return {
        "session_id": token,
        "total_time": int(total_time),
        "questions_answered": questions_answered,
        "completion_rate": completion_rate,
        "average_time_per_question": int(total_time / questions_answered) if questions_answered > 0 else 0,
        "performance_score": min(85, max(40, 60 + (questions_answered * 3))),  # Простая формула
        "created_at": session["created_at"].isoformat(),
        "completed_at": datetime.now(timezone.utc).isoformat()
    }

@router.get("/stats")
def get_stats():
    num_sessions = len(sessions)
    num_answers = sum(len(s["aeon_answers"]) for s in sessions.values())
    # Средний балл — если бы мы считали результаты (заглушка)
    avg_score = 50 if num_sessions > 0 else 0
    return {
        "sessions": num_sessions,
        "answers": num_answers,
        "avg_score": avg_score
    }

# ===== ИСПРАВЛЕННЫЕ AEON ЭНДПОИНТЫ =====

@router.post("/aeon/question/{token}")
async def aeon_next_question_with_token(token: str, data: dict = Body(...)):
    """Получить следующий вопрос AEON для конкретной сессии"""
    session = sessions.get(token)
    if not session:
        raise HTTPException(status_code=404, detail="Сессия не найдена")
    if is_token_expired(session):
        raise HTTPException(status_code=403, detail="Срок действия токена истёк")
    
    # Проверяем, сколько вопросов уже задано
    if session["current_question_index"] >= len(AEON_QUESTIONS):
        return JSONResponse(content={"detail": "Все вопросы заданы"}, status_code=404)
    
    # Получаем следующий вопрос
    question = AEON_QUESTIONS[session["current_question_index"]]
    
    # Проверяем, не задавали ли уже этот вопрос
    if question["id"] in session["asked_questions"]:
        # Ищем следующий незаданный вопрос
        for i in range(session["current_question_index"], len(AEON_QUESTIONS)):
            if AEON_QUESTIONS[i]["id"] not in session["asked_questions"]:
                question = AEON_QUESTIONS[i]
                session["current_question_index"] = i
                break
        else:
            return JSONResponse(content={"detail": "Все вопросы заданы"}, status_code=404)
    
    # Добавляем вопрос в список заданных
    session["asked_questions"].add(question["id"])
    
    log_event("aeon_question", {"token": token, "question_id": question["id"]})
    
    return {
        "question": question["text"],
        "type": question["type"],
        "question_id": question["id"]
    }

@router.post("/aeon/glyph/{token}")
async def generate_glyph_with_token(token: str, data: dict = Body(...)):
    """Сгенерировать глиф для конкретной сессии"""
    session = sessions.get(token)
    if not session:
        raise HTTPException(status_code=404, detail="Сессия не найдена")
    if is_token_expired(session):
        raise HTTPException(status_code=403, detail="Срок действия токена истёк")
    
    answers = session["aeon_answers"]
    log_event("generate_glyph", {"token": token, "answers_count": len(answers)})
    
    # Анализируем качество ответов
    answer_values = list(answers.values())
    if not answer_values:
        return {
            "glyph": "🚀 Стартер-Энтузиаст",
            "profile": "Кандидат только начинает своё интервью. Пока недостаточно данных для полного анализа."
        }
    
    avg_length = sum(len(str(answer)) for answer in answer_values) / len(answer_values)
    detailed_answers = sum(1 for answer in answer_values if len(str(answer)) > 50)
    detailed_percentage = (detailed_answers / len(answer_values)) * 100
    
    # Определяем профиль на основе качества ответов
    if detailed_percentage >= 70:
        glyph = "🎯 Лидер-Аналитик"
        profile = f"Кандидат продемонстрировал исключительную глубину мышления и аналитические способности. Средняя длина ответов: {int(avg_length)} символов. Показывает высокий уровень самрефлексии, стратегического мышления и готовности к лидерству. Отлично структурирует мысли и может детально объяснить свои решения."
    elif detailed_percentage >= 50:
        glyph = "⚡ Потенциал-Рост"
        profile = f"Кандидат показал хорошие коммуникативные навыки и потенциал для развития. Средняя длина ответов: {int(avg_length)} символов. Демонстрирует готовность к обучению, адаптивность и базовые профессиональные компетенции. Может эффективно работать в команде и брать на себя ответственность."
    else:
        glyph = "🚀 Стартер-Энтузиаст"
        profile = f"Кандидат показал энтузиазм и базовые навыки. Средняя длина ответов: {int(avg_length)} символов. Демонстрирует мотивацию к работе и готовность к профессиональному росту. Подходит для позиций начального уровня с хорошими перспективами развития."
    
    # Попытаемся использовать OpenAI для улучшения профиля
    try:
        if OPENAI_API_KEY and not OPENAI_API_KEY.startswith("sk-proj-X1"):  # Проверяем что это не тестовый ключ
            results = [{"question": q_id, "answer": answer} for q_id, answer in answers.items()]
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
                if response.status_code == 200:
                    content = response.json()["choices"][0]["message"]["content"]
                    try:
                        import json as pyjson
                        ai_result = pyjson.loads(content)
                        return ai_result
                    except:
                        pass  # Падаем на fallback
    except:
        pass  # Используем fallback
    
    return {"glyph": glyph, "profile": profile}

@router.post("/aeon/summary/{token}")
async def aeon_summary_with_token(token: str):
    """Сгенерировать сводку для конкретной сессии"""
    session = sessions.get(token)
    if not session:
        raise HTTPException(status_code=404, detail="Сессия не найдена")
    if is_token_expired(session):
        raise HTTPException(status_code=403, detail="Срок действия токена истёк")
    
    answers = session["aeon_answers"]
    total_answers = len(answers)
    
    if total_answers == 0:
        return {
            "summary": "📊 **Анализ интервью начат**\n\nИнтервью только началось. Пожалуйста, ответьте на вопросы для получения детального анализа."
        }
    
    # Анализируем ответы
    answer_values = list(answers.values())
    avg_length = sum(len(str(answer)) for answer in answer_values) / len(answer_values)
    detailed_answers = sum(1 for answer in answer_values if len(str(answer)) > 50)
    short_answers = sum(1 for answer in answer_values if len(str(answer)) < 20)
    
    # Вычисляем время сессии
    total_time = (datetime.now(timezone.utc) - session["created_at"]).total_seconds() / 60  # в минутах
    
    summary = f"""📊 **Анализ интервью завершен**

**Статистика интервью:**
• Отвечено на {total_answers} из {len(AEON_QUESTIONS)} вопросов
• Средняя длина ответа: {int(avg_length)} символов
• Детальных ответов: {detailed_answers} ({int((detailed_answers / total_answers) * 100)}%)
• Кратких ответов: {short_answers} ({int((short_answers / total_answers) * 100)}%)
• Общее время: {int(total_time)} минут

**Анализ качества ответов:**
{
    '✅ Отличное качество - кандидат предоставил подробные, thoughtful ответы на большинство вопросов' if detailed_answers >= 7 else
    '✅ Хорошее качество - кандидат дал содержательные ответы на половину вопросов' if detailed_answers >= 5 else
    '⚠️ Базовое качество - ответы краткие, рекомендуется более детальное собеседование'
}

**Рекомендации:**
• Кандидат готов к следующему этапу интервью
• Рекомендуется техническое интервью для проверки hard skills
• Показал {'высокий' if avg_length > 100 else 'средний' if avg_length > 50 else 'базовый'} уровень коммуникативных навыков"""

    log_event("aeon_summary", {"token": token, "answers_count": total_answers})
    
    return {"summary": summary}

@router.post("/aeon/task/{token}")
async def aeon_task_with_token(token: str, data: dict = Body(...)):
    """Сгенерировать задание для конкретной сессии"""
    session = sessions.get(token)
    if not session:
        raise HTTPException(status_code=404, detail="Сессия не найдена")
    if is_token_expired(session):
        raise HTTPException(status_code=403, detail="Срок действия токена истёк")
    
    candidate = data.get("candidate", "Кандидат")
    position = data.get("position", "Специалист")
    
    # Fallback задание
    task = f"Создайте план развития команды из 5 человек для {position}. Включите: 1) Анализ текущих навыков 2) Определение целей 3) План обучения 4) Метрики успеха 5) Временные рамки"
    example = "Пример: Анализ показал нехватку навыков в области проектного управления. Цель - повысить эффективность на 30%. План включает тренинги, менторство и практические проекты на 3 месяца."
    
    # Попытаемся использовать OpenAI
    try:
        if OPENAI_API_KEY and not OPENAI_API_KEY.startswith("sk-proj-X1"):
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
                if response.status_code == 200:
                    content = response.json()["choices"][0]["message"]["content"]
                    try:
                        import json as pyjson
                        result = pyjson.loads(content)
                        return result
                    except:
                        pass
    except:
        pass
    
    return {"task": task, "example": example}

# ===== СТАРЫЕ ЭНДПОИНТЫ (для обратной совместимости) =====

@router.post("/aeon/glyph")
async def generate_glyph_legacy(data: dict):
    """Старый эндпоинт для генерации глифа (без токена)"""
    results = data.get("results", [])
    log_event("generate_glyph_legacy", {"results": results})
    
    if not results:
        return {
            "glyph": "🚀 Стартер-Энтузиаст", 
            "profile": "Недостаточно данных для анализа"
        }
    
    # Простой анализ для legacy
    avg_length = sum(len(str(r.get('answer', ''))) for r in results) / len(results)
    
    if avg_length > 100:
        return {
            "glyph": "🎯 Лидер-Аналитик",
            "profile": "Кандидат показал отличные аналитические способности и глубину мышления."
        }
    elif avg_length > 50:
        return {
            "glyph": "⚡ Потенциал-Рост", 
            "profile": "Кандидат демонстрирует хороший потенциал и коммуникативные навыки."
        }
    else:
        return {
            "glyph": "🚀 Стартер-Энтузиаст",
            "profile": "Кандидат показал базовые навыки и мотивацию к развитию."
        }

@router.post("/aeon/question")
async def aeon_next_question_legacy(data: dict):
    """Старый эндпоинт для получения вопросов (без токена)"""
    history = data.get("history", [])
    
    if len(history) >= len(AEON_QUESTIONS):
        return {"question": None}
    
    # Возвращаем вопрос по индексу
    question = AEON_QUESTIONS[len(history)]
    return {
        "question": question["text"],
        "type": question["type"]
    }

@router.post("/aeon/summary")
async def aeon_summary_legacy(data: dict):
    """Старый эндпоинт для генерации сводки (без токена)"""
    history = data.get("history", [])
    
    if not history:
        return {
            "summary": "Недостаточно данных для анализа",
            "recommendation": "Необходимо ответить на вопросы"
        }
    
    return {
        "glyph": "📊 Анализ завершен",
        "summary": f"Кандидат ответил на {len(history)} вопросов. Показал базовые профессиональные навыки.",
        "recommendation": "Рекомендуется к дальнейшему рассмотрению"
    }

@router.post("/aeon/task")
async def aeon_task_legacy(data: dict):
    """Старый эндпоинт для генерации заданий (без токена)"""
    return {
        "task": "Опишите ваш подход к решению сложных задач",
        "example": "Анализирую проблему, разбиваю на части, ищу решения, тестирую и внедряю"
    }

# ===== ADMIN ENDPOINTS =====

@admin_router.get("/admin", response_class=HTMLResponse)
def admin_sessions(request: Request):
    session_list = [
        {
            "token": token, 
            "created_at": s["created_at"], 
            "completed": s["completed"], 
            "answers": len(s["aeon_answers"]),
            "total_answers": len(s["answers"])
        }
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
    total_aeon_answers = sum(len(s["aeon_answers"]) for s in sessions.values())
    return templates.TemplateResponse("admin_stats.html", {
        "request": request, 
        "total": total, 
        "completed": completed, 
        "active": active,
        "total_aeon_answers": total_aeon_answers
    })

@admin_router.get("/admin/log", response_class=HTMLResponse)
def admin_log(request: Request):
    return templates.TemplateResponse("admin_log.html", {"request": request, "log": list(reversed(log))})

@admin_router.get("/admin/export/sessions")
def export_sessions():
    def generate():
        output = StringIO()
        writer = csv.writer(output)
        writer.writerow(["token", "created_at", "completed", "answers", "aeon_answers"])
        for token, s in sessions.items():
            writer.writerow([token, s["created_at"], s["completed"], len(s["answers"]), len(s["aeon_answers"])])
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