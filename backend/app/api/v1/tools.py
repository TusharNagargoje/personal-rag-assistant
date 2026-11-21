"""Document-grounded utility endpoints."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.models import Chunk, Document, User
from app.db.session import get_db
from app.rag.generator import LLMGenerator
from app.schemas.tools import FAQGenerateRequest, SummarizeRequest

router = APIRouter(prefix="/tools", tags=["Document tools"])


async def _document_context(document_id: str, user: User, db: AsyncSession) -> tuple[Document, str]:
    result = await db.execute(select(Document).where(Document.id == document_id, Document.user_id == user.id))
    document = result.scalar_one_or_none()
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")
    chunks = await db.execute(select(Chunk).where(Chunk.document_id == document.id).order_by(Chunk.chunk_index))
    return document, "\n\n".join(c.content for c in chunks.scalars().all())[:30000]


@router.post("/summarize")
async def summarize(payload: SummarizeRequest, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    document, context = await _document_context(payload.document_id, user, db)
    if not context:
        raise HTTPException(status_code=409, detail="Document is not indexed yet")
    prompt = f"Summarize this source as {payload.summary_type}. Focus: {payload.focus_topic or 'main points'}. Cite claims with [1].\n\n{context}"
    summary = await LLMGenerator().generate_response(prompt, "Use only the supplied source. If unavailable, state that.")
    return {"document_id": document.id, "filename": document.filename, "summary": summary}


@router.post("/faq")
async def generate_faq(payload: FAQGenerateRequest, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    document, context = await _document_context(payload.document_id, user, db)
    if not context:
        raise HTTPException(status_code=409, detail="Document is not indexed yet")
    result = await LLMGenerator().generate_response(
        f"Create {payload.num_questions} useful FAQs from this source. Return numbered question and answer pairs.\n\n{context}",
        "Use only facts from the provided source.",
    )
    return {"document_id": document.id, "filename": document.filename, "faqs_markdown": result}
