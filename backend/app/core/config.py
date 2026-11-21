import os
from typing import List, Optional, Union
from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # General App Settings
    APP_NAME: str = "Personal RAG Assistant"
    APP_VERSION: str = "1.0.0"
    ENVIRONMENT: str = "development"
    DEBUG: bool = True
    LOG_LEVEL: str = "INFO"

    # Security
    SECRET_KEY: str = "super-secret-default-key-for-local-dev-at-least-32-chars-long"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # OAuth
    GOOGLE_CLIENT_ID: Optional[str] = None
    GOOGLE_CLIENT_SECRET: Optional[str] = None
    GOOGLE_REDIRECT_URI: str = "http://localhost:3000/api/auth/callback/google"

    # Database
    DATABASE_URL: str = "sqlite+aiosqlite:///./data/rag_assistant.db"

    # Redis (Optional)
    REDIS_URL: Optional[str] = None

    # Vector Store (Qdrant)
    QDRANT_URL: Optional[str] = None
    QDRANT_API_KEY: Optional[str] = None
    QDRANT_COLLECTION_NAME: str = "personal_rag_documents"

    # Embeddings
    EMBEDDING_PROVIDER: str = "sentence-transformers"  # sentence-transformers, gemini, openai
    EMBEDDING_MODEL_NAME: str = "BAAI/bge-small-en-v1.5"
    EMBEDDING_DIMENSION: int = 384

    # LLM Defaults & Keys
    DEFAULT_LLM_PROVIDER: str = "gemini"  # gemini, groq, openai, ollama
    DEFAULT_LLM_MODEL: str = "gemini-3.8-flash"
    DEFAULT_TEMPERATURE: float = 0.2
    DEFAULT_MAX_TOKENS: int = 2048

    GEMINI_API_KEY: Optional[str] = None
    GROQ_API_KEY: Optional[str] = None
    OPENAI_API_KEY: Optional[str] = None
    OLLAMA_BASE_URL: str = "http://localhost:11434"

    # RAG Retrieval Configuration
    RAG_TOP_K: int = 5
    RAG_SIMILARITY_THRESHOLD: float = 0.15
    RAG_ENABLE_HYBRID_SEARCH: bool = True
    RAG_BM25_WEIGHT: float = 0.3
    RAG_DENSE_WEIGHT: float = 0.7
    RAG_ENABLE_RERANKER: bool = False
    RAG_RERANKER_MODEL: str = "BAAI/bge-reranker-base"
    RAG_ENABLE_HYDE: bool = False
    RAG_ENABLE_MULTI_QUERY: bool = False

    # Chunking & Files
    DEFAULT_CHUNK_SIZE: int = 600
    DEFAULT_CHUNK_OVERLAP: int = 100
    MAX_UPLOAD_SIZE_MB: int = 50
    UPLOAD_DIR: str = os.path.join(os.getcwd(), "data", "uploads")

    # Networking & CORS
    BACKEND_HOST: str = "0.0.0.0"
    BACKEND_PORT: int = 8000
    CORS_ORIGINS: Union[List[str], str] = ["http://localhost:3000", "http://127.0.0.1:3000"]

    @model_validator(mode="after")
    def validate_production_secrets(self):
        if self.ENVIRONMENT.lower() == "production" and (
            len(self.SECRET_KEY) < 32 or self.SECRET_KEY.startswith("super-secret-default") or self.SECRET_KEY.startswith("change-me")
        ):
            raise ValueError("Set a unique SECRET_KEY of at least 32 characters in production")
        return self

    @field_validator("CORS_ORIGINS", mode="before")
    def parse_cors_origins(cls, v):
        if isinstance(v, str):
            if v.startswith("[") and v.endswith("]"):
                import json
                try:
                    return json.loads(v)
                except Exception:
                    pass
            return [origin.strip() for origin in v.split(",") if origin.strip()]
        return v


settings = Settings()
