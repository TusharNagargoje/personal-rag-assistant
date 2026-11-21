from typing import Optional
from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field


class CollectionCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    description: Optional[str] = None
    color: Optional[str] = "#3B82F6"
    icon: Optional[str] = "folder"


class CollectionUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=128)
    description: Optional[str] = None
    color: Optional[str] = None
    icon: Optional[str] = None


class CollectionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    user_id: str
    name: str
    description: Optional[str] = None
    color: str
    icon: str
    document_count: Optional[int] = 0
    created_at: datetime
    updated_at: datetime

