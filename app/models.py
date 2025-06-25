from typing import List, Optional
from pydantic import BaseModel

class Answer(BaseModel):
    id: int
    text: str

class Question(BaseModel):
    id: int
    text: str
    answers: List[Answer]

class Test(BaseModel):
    id: int
    title: str
    questions: List[Question]

class UserAnswer(BaseModel):
    question_id: int
    answer_id: int

class Result(BaseModel):
    id: int
    test_id: int
    score: int
    details: Optional[str] = None