from typing import List
from pydantic import BaseModel
from .models import UserAnswer

class SubmitAnswersRequest(BaseModel):
    answers: List[UserAnswer]

class SubmitAnswersResponse(BaseModel):
    result_id: int

class GetResultResponse(BaseModel):
    score: int
    details: str