from fastapi import APIRouter, HTTPException, status, Body, Request
from app.models import Test, Question, Answer
from app.schemas import SubmitAnswersRequest, SubmitAnswersResponse, GetResultResponse
from typing import Optional, Dict, List, Any
import uuid
import os
import httpx
from fastapi.responses import JSONResponse, HTMLResponse, StreamingResponse
from datetime import datetime, timedelta, timezone
from fastapi.templating import Jinja2Templates
import csv
from io import StringIO
from dataclasses import dataclass, field

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

# Улучшенная структура для отслеживания сессий
@dataclass
class SessionState:
    answers: List[Dict] = field(default_factory=list)
    aeon_answers: Dict[str, str] = field(default_factory=dict)
    asked_questions: set = field(default_factory=set)
    current_question_index: int = 0
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    completed: bool = False
    question_order: List[str] = field(default_factory=list)  # Порядок заданных вопросов
    last_activity: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

# AEON Questions Pool - 10 профессиональных вопросов
AEON_QUESTIONS = [
    {
        "id": "q_1",
        "text": "Расскажите о себе и своем профессиональном опыте. Какие навыки и достижения вы считаете наиболее важными?",
        "type": "technical",
        "keywords": ["навыки", "опыт", "достижения", "профессионал"]
    },
    {
        "id": "q_2", 
        "text": "Опишите свой идеальный рабочий день. Что бы вы делали и как бы себя чувствовали?",
        "type": "soft",
        "keywords": ["мотивация", "идеал", "комфорт", "рабочий день"]
    },
    {
        "id": "q_3",
        "text": "Расскажите о ситуации, когда вам пришлось решать сложную проблему. Как вы подошли к решению?",
        "type": "technical",
        "keywords": ["проблема", "решение", "анализ", "подход"]
    },
    {
        "id": "q_4",
        "text": "Как вы справляетесь со стрессом и давлением на работе? Приведите конкретный пример.",
        "type": "soft",
        "keywords": ["стресс", "давление", "пример", "справляться"]
    },
    {
        "id": "q_5",
        "text": "Расскажите о своем опыте работы в команде. Какую роль вы обычно играете в коллективе?",
        "type": "soft",
        "keywords": ["команда", "роль", "коллектив", "сотрудничество"]
    },
    {
        "id": "q_6",
        "text": "Какие технологии, методы или навыки вы изучили за последний год? Что планируете изучить?",
        "type": "technical",
        "keywords": ["технологии", "обучение", "планы", "развитие"]
    },
    {
        "id": "q_7",
        "text": "Опишите ситуацию, когда вам пришлось адаптироваться к серьезным изменениям. Как вы это делали?",
        "type": "soft",
        "keywords": ["адаптация", "изменения", "гибкость", "приспособление"]
    },
    {
        "id": "q_8",
        "text": "Расскажите о своих карьерных целях. Где вы видите себя через 2-3 года?",
        "type": "soft",
        "keywords": ["карьера", "цели", "планы", "будущее"]
    },
    {
        "id": "q_9",
        "text": "Что мотивирует вас в работе больше всего? Что дает вам энергию для профессионального роста?",
        "type": "soft",
        "keywords": ["мотивация", "энергия", "рост", "драйв"]
    },
    {
        "id": "q_10",
        "text": "Почему вы заинтересованы в работе в нашей компании? Какой вклад вы хотите внести?",
        "type": "soft",
        "keywords": ["интерес", "компания", "вклад", "ценность"]
    }
]

# Улучшенная система хранения сессий
sessions: Dict[str, SessionState] = {}

SESSION_TTL = timedelta(hours=1)

def is_token_expired(session_state: SessionState) -> bool:
    """Проверка истечения срока действия токена"""
    return datetime.now(timezone.utc) > session_state.created_at + SESSION_TTL

def update_session_activity(session_state: SessionState):
    """Обновление времени последней активности"""
    session_state.last_activity = datetime.now(timezone.utc)

def analyze_answer_quality(answer: str, question_keywords: List[str]) -> Dict[str, Any]:
    """Анализ качества ответа на основе содержания и ключевых слов"""
    if not answer or not isinstance(answer, str):
        return {"score": 0, "details": "Пустой ответ"}
    
    answer_lower = answer.lower()
    
    # Базовые метрики
    word_count = len(answer.split())
    sentence_count = len([s for s in answer.split('.') if s.strip()])
    
    # Анализ содержания
    keyword_matches = sum(1 for keyword in question_keywords if keyword.lower() in answer_lower)
    keyword_ratio = keyword_matches / len(question_keywords) if question_keywords else 0
    
    # Анализ структуры
    has_examples = any(word in answer_lower for word in ['например', 'пример', 'случай', 'ситуация'])
    has_specifics = any(word in answer_lower for word in ['конкретно', 'именно', 'определенно'])
    
    # Оценка качества (0-100)
    score = 0
    
    # Базовая оценка по длине
    if word_count >= 50:
        score += 30
    elif word_count >= 20:
        score += 20
    elif word_count >= 10:
        score += 10
    
    # Бонус за релевантность
    score += min(30, keyword_ratio * 100)
    
    # Бонус за примеры и конкретику
    if has_examples:
        score += 15
    if has_specifics:
        score += 10
    
    # Бонус за структурированность
    if sentence_count >= 3:
        score += 10
    elif sentence_count >= 2:
        score += 5
    
    # Штраф за слишком краткие ответы
    if word_count < 5:
        score = min(score, 10)
    
    return {
        "score": min(100, max(0, score)),
        "word_count": word_count,
        "sentence_count": sentence_count,
        "keyword_matches": keyword_matches,
        "keyword_ratio": keyword_ratio,
        "has_examples": has_examples,
        "has_specifics": has_specifics
    }

def calculate_performance_score(session_state: SessionState) -> int:
    """Расчет итогового балла на основе качества ответов"""
    if not session_state.aeon_answers:
        return 0
    
    total_score = 0
    answered_questions = 0
    
    for question_id, answer in session_state.aeon_answers.items():
        # Найти вопрос для получения ключевых слов
        question_data = next((q for q in AEON_QUESTIONS if q["id"] == question_id), None)
        if question_data:
            keywords = question_data.get("keywords", [])
            quality = analyze_answer_quality(answer, keywords)
            total_score += quality["score"]
            answered_questions += 1
    
    if answered_questions == 0:
        return 0
    
    # Средний балл за качество ответов
    avg_quality = total_score / answered_questions
    
    # Бонус за полноту (процент отвеченных вопросов)
    completion_bonus = (answered_questions / len(AEON_QUESTIONS)) * 20
    
    # Итоговый балл
    final_score = min(100, max(0, avg_quality + completion_bonus))
    
    return int(final_score)

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
    """Создание новой сессии с улучшенным отслеживанием"""
    token = str(uuid.uuid4())
    sessions[token] = SessionState()
    log_event("create_session", {"token": token})
    return {"token": token}

@router.post("/session/{token}/answer")
def save_answer(token: str, answer: dict = Body(...)):
    """Сохранение ответа с валидацией"""
    session_state = sessions.get(token)
    if not session_state:
        raise HTTPException(status_code=404, detail="Сессия не найдена")
    if is_token_expired(session_state):
        raise HTTPException(status_code=403, detail="Срок действия токена истёк")
    if session_state.completed:
        raise HTTPException(status_code=403, detail="Тест уже завершён")
    
    # Обновляем активность
    update_session_activity(session_state)
    
    # Сохраняем обычный ответ
    session_state.answers.append(answer)
    
    # Если это AEON ответ, сохраняем отдельно с валидацией
    if "question_id" in answer:
        question_id = answer["question_id"]
        # Проверяем, что этот вопрос действительно был задан
        if question_id in session_state.asked_questions:
            session_state.aeon_answers[question_id] = answer.get("answer", "")
        else:
            log_event("invalid_answer", {"token": token, "question_id": question_id, "error": "Question not asked"})
            raise HTTPException(status_code=400, detail="Вопрос не был задан")
    
    log_event("save_answer", {"token": token, "answer": answer})
    return {"status": "saved"}

@router.get("/session/{token}")
def get_session(token: str):
    """Получение состояния сессии"""
    session_state = sessions.get(token)
    if not session_state:
        raise HTTPException(status_code=404, detail="Сессия не найдена")
    if is_token_expired(session_state):
        raise HTTPException(status_code=403, detail="Срок действия токена истёк")
    
    return {
        "token": token,
        "created_at": session_state.created_at,
        "completed": session_state.completed,
        "questions_answered": len(session_state.aeon_answers),
        "total_questions": len(AEON_QUESTIONS),
        "asked_questions": len(session_state.asked_questions),
        "current_performance": calculate_performance_score(session_state)
    }

@router.post("/session/{token}/complete")
def complete_session(token: str):
    session_state = sessions.get(token)
    if not session_state:
        raise HTTPException(status_code=404, detail="Сессия не найдена")
    if is_token_expired(session_state):
        raise HTTPException(status_code=403, detail="Срок действия токена истёк")
    session_state.completed = True
    log_event("complete_session", {"token": token})
    return {"status": "completed"}

@router.get("/result/{token}")
def get_result_by_token(token: str):
    session_state = sessions.get(token)
    if not session_state:
        raise HTTPException(status_code=404, detail="Сессия не найдена")
    
    total_time = (datetime.now(timezone.utc) - session_state.created_at).total_seconds()
    questions_answered = len(session_state.aeon_answers)
    completion_rate = (questions_answered / len(AEON_QUESTIONS)) * 100 if len(AEON_QUESTIONS) > 0 else 0
    
    return {
        "session_id": token,
        "total_time": int(total_time),
        "questions_answered": questions_answered,
        "completion_rate": completion_rate,
        "average_time_per_question": int(total_time / questions_answered) if questions_answered > 0 else 0,
        "performance_score": min(85, max(40, 60 + (questions_answered * 3))),  # Простая формула
        "created_at": session_state.created_at.isoformat(),
        "completed_at": datetime.now(timezone.utc).isoformat()
    }

@router.get("/stats")
def get_stats():
    num_sessions = len(sessions)
    num_answers = sum(len(s.aeon_answers) for s in sessions.values())
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
    """ИСПРАВЛЕННАЯ логика получения следующего вопроса AEON"""
    session_state = sessions.get(token)
    if not session_state:
        raise HTTPException(status_code=404, detail="Сессия не найдена")
    if is_token_expired(session_state):
        raise HTTPException(status_code=403, detail="Срок действия токена истёк")
    
    # Обновляем активность
    update_session_activity(session_state)
    
    # Ищем первый незаданный вопрос
    available_questions = [q for q in AEON_QUESTIONS if q["id"] not in session_state.asked_questions]
    
    if not available_questions:
        return JSONResponse(content={"detail": "Все вопросы заданы"}, status_code=404)
    
    # Берем первый доступный вопрос
    question = available_questions[0]
    
    # ИСПРАВЛЕНИЕ: Добавляем вопрос в список заданных ТОЛЬКО после успешной отправки
    session_state.asked_questions.add(question["id"])
    session_state.question_order.append(question["id"])
    
    log_event("aeon_question", {"token": token, "question_id": question["id"]})
    
    return {
        "question": question["text"],
        "type": question["type"],
        "question_id": question["id"],
        "question_number": len(session_state.asked_questions),
        "total_questions": len(AEON_QUESTIONS)
    }

@router.post("/aeon/glyph/{token}")
async def generate_glyph_with_token(token: str, data: dict = Body(...)):
    """УЛУЧШЕННАЯ генерация глифа с анализом качества ответов"""
    session_state = sessions.get(token)
    if not session_state:
        raise HTTPException(status_code=404, detail="Сессия не найдена")
    if is_token_expired(session_state):
        raise HTTPException(status_code=403, detail="Срок действия токена истёк")
    
    answers = session_state.aeon_answers
    log_event("generate_glyph", {"token": token, "answers_count": len(answers)})
    
    if not answers:
        return {
            "glyph": "🚀 Стартер-Потенциал",
            "profile": "Кандидат только начинает интервью. Пока недостаточно данных для полного анализа."
        }
    
    # Анализируем качество ответов
    total_quality_score = 0
    quality_details = []
    
    for question_id, answer in answers.items():
        question_data = next((q for q in AEON_QUESTIONS if q["id"] == question_id), None)
        if question_data:
            keywords = question_data.get("keywords", [])
            quality = analyze_answer_quality(answer, keywords)
            total_quality_score += quality["score"]
            quality_details.append(quality)
    
    avg_quality = total_quality_score / len(answers) if answers else 0
    completion_rate = (len(answers) / len(AEON_QUESTIONS)) * 100
    
    # Анализируем типы ответов
    technical_count = sum(1 for q_id in answers.keys() 
                         if any(q["id"] == q_id and q["type"] == "technical" for q in AEON_QUESTIONS))
    soft_count = len(answers) - technical_count
    
    # Определяем профиль на основе комплексного анализа
    if avg_quality >= 80:
        glyph = "🎯 Мастер-Лидер"
        profile = f"Исключительный кандидат с выдающимися навыками. Средний качественный балл: {avg_quality:.1f}/100. Демонстрирует глубокое понимание вопросов, структурированное мышление и высокий уровень профессиональной зрелости. Готов к лидерским позициям и сложным задачам."
    elif avg_quality >= 65:
        glyph = "⚡ Эксперт-Драйвер"
        profile = f"Сильный кандидат с хорошими профессиональными навыками. Средний качественный балл: {avg_quality:.1f}/100. Показывает способность к аналитическому мышлению, может эффективно решать сложные задачи и работать в команде."
    elif avg_quality >= 50:
        glyph = "🌟 Потенциал-Рост"
        profile = f"Перспективный кандидат с хорошим потенциалом. Средний качественный балл: {avg_quality:.1f}/100. Демонстрирует базовые профессиональные навыки и мотивацию к развитию. Подходит для позиций с возможностью роста."
    else:
        glyph = "🚀 Стартер-Энтузиаст"
        profile = f"Кандидат на начальном этапе развития. Средний качественный балл: {avg_quality:.1f}/100. Показывает энтузиазм и готовность к обучению. Рекомендуется для junior позиций с менторской поддержкой."
    
    # Добавляем детали анализа
    profile += f"\n\n📊 Детали анализа:\n"
    profile += f"• Завершенность: {completion_rate:.1f}% ({len(answers)}/{len(AEON_QUESTIONS)})\n"
    profile += f"• Технические вопросы: {technical_count}, Soft skills: {soft_count}\n"
    profile += f"• Среднее качество ответов: {avg_quality:.1f}/100"
    
    return {"glyph": glyph, "profile": profile}

@router.post("/aeon/summary/{token}")
async def aeon_summary_with_token(token: str):
    """УЛУЧШЕННАЯ генерация сводки с детальным анализом"""
    session_state = sessions.get(token)
    if not session_state:
        raise HTTPException(status_code=404, detail="Сессия не найдена")
    if is_token_expired(session_state):
        raise HTTPException(status_code=403, detail="Срок действия токена истёк")
    
    answers = session_state.aeon_answers
    total_answers = len(answers)
    
    if total_answers == 0:
        return {
            "summary": "📊 **Анализ интервью начат**\n\nИнтервью только началось. Пожалуйста, ответьте на вопросы для получения детального анализа."
        }
    
    # Детальный анализ ответов
    quality_scores = []
    keyword_matches = []
    has_examples_count = 0
    
    for question_id, answer in answers.items():
        question_data = next((q for q in AEON_QUESTIONS if q["id"] == question_id), None)
        if question_data:
            keywords = question_data.get("keywords", [])
            quality = analyze_answer_quality(answer, keywords)
            quality_scores.append(quality["score"])
            keyword_matches.append(quality["keyword_matches"])
            if quality["has_examples"]:
                has_examples_count += 1
    
    # Расчет метрик
    avg_quality = sum(quality_scores) / len(quality_scores) if quality_scores else 0
    performance_score = calculate_performance_score(session_state)
    total_time = (datetime.now(timezone.utc) - session_state.created_at).total_seconds() / 60
    
    # Определение уровня качества
    if avg_quality >= 80:
        quality_level = "🏆 Превосходное"
        recommendation = "Настоятельно рекомендуется к найму"
    elif avg_quality >= 65:
        quality_level = "✅ Отличное"
        recommendation = "Рекомендуется к найму"
    elif avg_quality >= 50:
        quality_level = "👍 Хорошее"
        recommendation = "Подходит для рассмотрения"
    else:
        quality_level = "⚠️ Базовое"
        recommendation = "Требует дополнительного интервью"
    
    summary = f"""📊 **Подробный анализ интервью**

**Общая статистика:**
• Отвечено на {total_answers} из {len(AEON_QUESTIONS)} вопросов ({(total_answers/len(AEON_QUESTIONS)*100):.1f}%)
• Общее время интервью: {int(total_time)} минут
• Итоговый балл: {performance_score}/100

**Анализ качества ответов:**
• Уровень качества: {quality_level}
• Средний балл качества: {avg_quality:.1f}/100
• Ответы с примерами: {has_examples_count}/{total_answers}
• Релевантность содержания: {(sum(keyword_matches)/len(keyword_matches)/4*100):.1f}% (в среднем)

**Профессиональная оценка:**
{recommendation}

**Рекомендации для следующих этапов:**
• {'Техническое интервью с сложными задачами' if avg_quality >= 70 else 'Техническое интервью базового уровня'}
• {'Готов к самостоятельной работе' if performance_score >= 70 else 'Рекомендуется менторская поддержка'}
• {'Может претендовать на лидерские позиции' if avg_quality >= 80 else 'Подходит для командных позиций'}

**Сильные стороны:**
{f'• Высокое качество ответов и аналитическое мышление' if avg_quality >= 70 else ''}
{f'• Способность приводить конкретные примеры' if has_examples_count >= total_answers/2 else ''}
{f'• Хорошая скорость реакции' if total_time <= 30 else ''}"""

    log_event("aeon_summary", {"token": token, "answers_count": total_answers, "performance_score": performance_score})
    
    return {"summary": summary}

@router.post("/aeon/task/{token}")
async def aeon_task_with_token(token: str, data: dict = Body(...)):
    """Сгенерировать задание для конкретной сессии"""
    session_state = sessions.get(token)
    if not session_state:
        raise HTTPException(status_code=404, detail="Сессия не найдена")
    if is_token_expired(session_state):
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
            "created_at": s.created_at, 
            "completed": s.completed, 
            "answers": len(s.aeon_answers),
            "total_answers": len(s.answers)
        }
        for token, s in sessions.items()
    ]
    return templates.TemplateResponse("admin_sessions.html", {"request": request, "sessions": session_list})

@admin_router.get("/admin/session/{token}", response_class=HTMLResponse)
def admin_session_detail(request: Request, token: str):
    session_state = sessions.get(token)
    if not session_state:
        return HTMLResponse("<h2>Сессия не найдена</h2>", status_code=404)
    return templates.TemplateResponse("admin_session_detail.html", {"request": request, "token": token, "session": session_state})

@admin_router.post("/admin/session/{token}/delete")
def admin_delete_session(request: Request, token: str):
    sessions.pop(token, None)
    log_event("delete_session", {"token": token})
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/admin", status_code=303)

@admin_router.get("/admin/stats", response_class=HTMLResponse)
def admin_stats(request: Request):
    total = len(sessions)
    completed = sum(1 for s in sessions.values() if s.completed)
    active = total - completed
    total_aeon_answers = sum(len(s.aeon_answers) for s in sessions.values())
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
            writer.writerow([token, s.created_at, s.completed, len(s.answers), len(s.aeon_answers)])
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