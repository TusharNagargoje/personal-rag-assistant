from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel, ConfigDict


class IngestUrlRequest(BaseModel):
    url: str
    collection_id: Optional[str] = None
    title: Optional[str] = None


class IngestYoutubeRequest(BaseModel):
    youtube_url: str
    collection_id: Optional[str] = None
    title: Optional[str] = None


class ChunkResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    chunk_index: int
    content: str
    page_number: Optional[int] = None
    section_name: Optional[str] = None
    created_at: datetime



class DocumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    collection_id: Optional[str] = None
    user_id: str
    filename: str
    file_type: str
    file_size_bytes: int
    file_hash: str
    source_url: Optional[str] = None
    status: str
    error_message: Optional[str] = None
    chunk_count: int
    token_count: int
    created_at: datetime



class DocumentDetailResponse(DocumentResponse):
    chunks: List[ChunkResponse] = []
