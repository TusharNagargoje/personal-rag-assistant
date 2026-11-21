from typing import Optional, List
from pydantic import BaseModel, Field


class SummarizeRequest(BaseModel):
    document_id: str
    focus_topic: Optional[str] = None
    summary_type: str = "bullet_points"  # "executive", "bullet_points", "deep_dive"


class SummarizeResponse(BaseModel):
    document_id: str
    filename: str
    summary: str


class FAQItem(BaseModel):
    question: str
    answer: str


class FAQGenerateRequest(BaseModel):
    document_id: str
    num_questions: int = Field(5, ge=1, le=15)


class FAQGenerateResponse(BaseModel):
    document_id: str
    faqs: List[FAQItem]


class QuizOption(BaseModel):
    key: str  # "A", "B", "C", "D"
    text: str


class QuizQuestion(BaseModel):
    question: str
    options: List[QuizOption]
    correct_option: str
    explanation: str


class QuizGenerateRequest(BaseModel):
    document_id: str
    num_questions: int = Field(5, ge=1, le=10)


class QuizGenerateResponse(BaseModel):
    document_id: str
    questions: List[QuizQuestion]


class DocumentCompareRequest(BaseModel):
    document_id_a: str
    document_id_b: str
    comparison_criteria: Optional[str] = "Key differences, unique points in each, and shared topics"


class DocumentCompareResponse(BaseModel):
    doc_a_name: str
    doc_b_name: str
    comparison_markdown: str
