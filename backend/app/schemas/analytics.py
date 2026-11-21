from typing import Optional, List, Dict, Any
from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field


class FeedbackCreate(BaseModel):
    message_id: str
    score: int = Field(..., ge=-1, le=1)  # +1 or -1
    comment: Optional[str] = None


class FeedbackResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    message_id: str
    user_id: str
    score: int
    comment: Optional[str] = None
    created_at: datetime



class DayQueryCount(BaseModel):
    date: str
    queries: int


class LatencyBucket(BaseModel):
    range: str
    count: int


class AnalyticsSummaryResponse(BaseModel):
    total_documents: int
    total_chunks: int
    total_chat_sessions: int
    total_queries: int
    avg_latency_ms: float
    positive_feedback_count: int
    negative_feedback_count: int
    feedback_satisfaction_pct: float
    queries_trend: List[DayQueryCount] = []
    top_sources: List[Dict[str, Any]] = []


class UserSettingsUpdate(BaseModel):
    default_llm_provider: Optional[str] = None
    default_llm_model: Optional[str] = None
    gemini_api_key: Optional[str] = None
    groq_api_key: Optional[str] = None
    openai_api_key: Optional[str] = None
    temperature: Optional[float] = None
    top_k: Optional[int] = None
