"""FastAPI application entry point."""
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse

from app.api.deps import check_rate_limit
from app.api.v1 import auth, chat, collections, documents, feedback, tools
from app.core.config import settings
from app.core.logging import logger
from app.db.session import engine, init_db
from app.rag.index_state import rebuild_sparse_index
from sqlalchemy import text


@asynccontextmanager
async def lifespan(_: FastAPI):
    await init_db()
    await rebuild_sparse_index()
    logger.info("Personal RAG Assistant API started")
    yield


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="Private, source-grounded search and chat over your documents.",
    openapi_url="/openapi.json" if settings.ENVIRONMENT != "production" else None,
    docs_url="/docs" if settings.ENVIRONMENT != "production" else None,
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Accept"],
)
app.add_middleware(GZipMiddleware, minimum_size=1000)


@app.middleware("http")
async def security_headers(request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=()"
    return response


@app.get("/health", tags=["System"])
async def health():
    return {"status": "ok", "version": settings.APP_VERSION}


@app.get("/ready", tags=["System"])
async def ready():
    async with engine.connect() as connection:
        await connection.execute(text("SELECT 1"))
    return JSONResponse({"status": "ready"})


for router in (auth.router, collections.router, documents.router, chat.router, tools.router, feedback.router):
    app.include_router(router, prefix="/api/v1", dependencies=[Depends(check_rate_limit)])
