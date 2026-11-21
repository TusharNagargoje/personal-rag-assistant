"""Rebuild the in-process sparse index after API restarts."""
import json

from sqlalchemy import select

from app.db.models import Chunk
from app.db.session import async_session_factory
from app.rag.retrieval import bm25_retriever


async def rebuild_sparse_index() -> None:
    async with async_session_factory() as session:
        result = await session.execute(select(Chunk).order_by(Chunk.created_at))
        chunks = result.scalars().all()
    bm25_retriever.update_index(
        chunk_ids=[chunk.id for chunk in chunks],
        doc_ids=[chunk.document_id for chunk in chunks],
        texts=[chunk.content for chunk in chunks],
        metadatas=[json.loads(chunk.metadata_json or "{}") for chunk in chunks],
        collection_ids=[chunk.collection_id for chunk in chunks],
    )
