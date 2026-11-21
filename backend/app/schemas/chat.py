from typing import Optional, List, Dict, Any
from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field


class CitationItem(BaseModel):
    citation_id: int  # 1, 2, 3...
    chunk_id: str
    document_id: str
    filename: str
    page_number: Optional[int] = None
    section_name: Optional[str] = None
    snippet: str
    score: Optional[float] = None


class ChatMessageCreate(BaseModel):
    content: str = Field(..., min_length=1, max_length=12000)
    collection_id: Optional[str] = None
    document_ids: Optional[List[str]] = None
    stream: bool = True
    llm_provider: Optional[str] = None
    llm_model: Optional[str] = None
    temperature: Optional[float] = None
    llm_api_key: Optional[str] = Field(None, min_length=8, max_length=512)


class ChatMessageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    session_id: str
    role: str
    content: str
    citations: List[CitationItem] = []
    model_used: Optional[str] = None
    tokens_used: int = 0
    latency_ms: int = 0
    created_at: datetime
    feedback: Optional[Dict[str, Any]] = None



class ChatSessionCreate(BaseModel):
    title: Optional[str] = "New Chat"
    collection_id: Optional[str] = None


class ChatSessionUpdate(BaseModel):
    title: Optional[str] = None
    is_pinned: Optional[bool] = None


class ChatSessionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    user_id: str
    collection_id: Optional[str] = None
    title: str
    is_pinned: bool
    created_at: datetime
    updated_at: datetime
    messages: List[ChatMessageResponse] = []

