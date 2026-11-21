"""Conversation and grounded question answering endpoints."""
import json
import time
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.guardrails import check_prompt_injection, sanitize_input
from app.db.models import ChatMessage, ChatSession, Collection, Document, User
from app.db.session import get_db
from app.rag.citations import build_citation_items
from app.rag.generator import LLMGenerator
from app.rag.retrieval import hybrid_retrieve
from app.schemas.chat import ChatMessageCreate, ChatSessionCreate, ChatSessionUpdate

router = APIRouter(prefix="/chat", tags=["Chat"])


def _message_payload(message: ChatMessage) -> dict[str, Any]:
    try:
        citations = json.loads(message.citations_json or "[]")
    except (TypeError, json.JSONDecodeError):
        citations = []
    return {
        "id": message.id,
        "session_id": message.session_id,
        "role": message.role,
        "content": message.content,
        "citations": citations,
        "model_used": message.model_used,
        "tokens_used": message.tokens_used,
        "latency_ms": message.latency_ms,
        "created_at": message.created_at,
    }


async def _owned_session(session_id: str, user: User, db: AsyncSession) -> ChatSession:
    result = await db.execute(
        select(ChatSession).where(ChatSession.id == session_id, ChatSession.user_id == user.id)
    )
    session = result.scalar_one_or_none()
    if session is None:
        raise HTTPException(status_code=404, detail="Chat not found")
    return session


@router.get("/sessions")
async def list_sessions(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(ChatSession).where(ChatSession.user_id == user.id).order_by(ChatSession.updated_at.desc())
    )
    return [{"id": s.id, "title": s.title, "collection_id": s.collection_id,
             "is_pinned": s.is_pinned, "created_at": s.created_at, "updated_at": s.updated_at}
            for s in result.scalars().all()]


@router.post("/sessions", status_code=201)
async def create_session(payload: ChatSessionCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if payload.collection_id:
        collection = await db.scalar(select(Collection).where(Collection.id == payload.collection_id, Collection.user_id == user.id))
        if collection is None:
            raise HTTPException(status_code=404, detail="Collection not found")
    session = ChatSession(user_id=user.id, title=(payload.title or "New Chat")[:255], collection_id=payload.collection_id)
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return {"id": session.id, "title": session.title, "collection_id": session.collection_id,
            "is_pinned": session.is_pinned, "created_at": session.created_at}


@router.get("/sessions/{session_id}")
async def get_session(session_id: str, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    session = await _owned_session(session_id, user, db)
    result = await db.execute(
        select(ChatMessage).where(ChatMessage.session_id == session.id).order_by(ChatMessage.created_at.asc())
    )
    return {"id": session.id, "title": session.title, "collection_id": session.collection_id,
            "messages": [_message_payload(m) for m in result.scalars().all()]}


@router.patch("/sessions/{session_id}")
async def update_session(session_id: str, payload: ChatSessionUpdate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    session = await _owned_session(session_id, user, db)
    if payload.title is not None:
        session.title = payload.title.strip()[:255] or "New Chat"
    if payload.is_pinned is not None:
        session.is_pinned = payload.is_pinned
    await db.commit()
    return {"id": session.id, "title": session.title, "is_pinned": session.is_pinned}


@router.delete("/sessions/{session_id}", status_code=204)
async def delete_session(session_id: str, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    session = await _owned_session(session_id, user, db)
    await db.delete(session)
    await db.commit()


@router.post("/sessions/{session_id}/messages")
async def ask(session_id: str, payload: ChatMessageCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    session = await _owned_session(session_id, user, db)
    question = sanitize_input(payload.content)
    suspicious, reason = check_prompt_injection(question)
    if suspicious:
        raise HTTPException(status_code=400, detail=reason)
    if not question:
        raise HTTPException(status_code=422, detail="Question cannot be empty")
    if payload.collection_id and session.collection_id and payload.collection_id != session.collection_id:
        raise HTTPException(status_code=400, detail="Chat collection does not match the selected collection")

    collection_id = payload.collection_id or session.collection_id
    if collection_id:
        collection = await db.scalar(select(Collection).where(Collection.id == collection_id, Collection.user_id == user.id))
        if collection is None:
            raise HTTPException(status_code=404, detail="Collection not found")
    owned_docs = select(Document.id).where(Document.user_id == user.id, Document.status == "indexed")
    if collection_id:
        owned_docs = owned_docs.where(Document.collection_id == collection_id)
    if payload.document_ids:
        requested = set(payload.document_ids)
        owned_result = await db.execute(owned_docs.where(Document.id.in_(requested)))
        allowed_doc_ids = [row[0] for row in owned_result.all()]
        if len(allowed_doc_ids) != len(requested):
            raise HTTPException(status_code=404, detail="One or more selected documents were not found")
    else:
        owned_result = await db.execute(owned_docs)
        allowed_doc_ids = [row[0] for row in owned_result.all()]

    start = time.perf_counter()
    history_result = await db.execute(
        select(ChatMessage).where(ChatMessage.session_id == session.id).order_by(ChatMessage.created_at.desc()).limit(8)
    )
    history = [{"role": m.role, "content": m.content} for m in reversed(history_result.scalars().all())]
    try:
        chunks = await hybrid_retrieve(question, collection_id=collection_id, document_ids=allowed_doc_ids)
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Retrieval is temporarily unavailable") from exc

    citations = [item.model_dump() for item in build_citation_items(chunks)]
    prompt_provider = payload.llm_provider
    generator = LLMGenerator(provider=prompt_provider, model=payload.llm_model, api_key=payload.llm_api_key, temperature=payload.temperature)
    user_message = ChatMessage(session_id=session.id, role="user", content=question)
    db.add(user_message)
    await db.commit()

    async def event_stream():
        answer_parts: list[str] = []
        try:
            async for token in generator.stream_rag_response(question, chunks, history):
                answer_parts.append(token)
                yield f"data: {json.dumps({'type': 'token', 'text': token}, ensure_ascii=False)}\n\n"
            answer = "".join(answer_parts).strip()
            assistant = ChatMessage(
                session_id=session.id, role="assistant", content=answer,
                citations_json=json.dumps(citations, ensure_ascii=False),
                model_used=generator.model, latency_ms=int((time.perf_counter() - start) * 1000),
            )
            db.add(assistant)
            session.title = session.title if session.title != "New Chat" else question[:80]
            await db.commit()
            yield f"data: {json.dumps({'type': 'done', 'citations': citations, 'message_id': assistant.id}, ensure_ascii=False)}\n\n"
        except Exception:
            await db.rollback()
            yield f"data: {json.dumps({'type': 'error', 'message': 'The response could not be completed.'})}\n\n"
        yield "data: [DONE]\n\n"

    if payload.stream:
        return StreamingResponse(event_stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    answer = "".join([token async for token in generator.stream_rag_response(question, chunks, history)])
    assistant = ChatMessage(session_id=session.id, role="assistant", content=answer, citations_json=json.dumps(citations),
                            model_used=generator.model, latency_ms=int((time.perf_counter() - start) * 1000))
    db.add(assistant)
    await db.commit()
    await db.refresh(assistant)
    return _message_payload(assistant)
