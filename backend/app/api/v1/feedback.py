"""Answer feedback and lightweight analytics endpoints."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.models import ChatMessage, ChatSession, Document, Feedback, User
from app.db.session import get_db
from app.schemas.analytics import FeedbackCreate

router = APIRouter(tags=["Feedback & Analytics"])


@router.post("/feedback", status_code=201)
async def submit_feedback(payload: FeedbackCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(ChatMessage).join(ChatSession).where(
            ChatMessage.id == payload.message_id,
            ChatMessage.role == "assistant",
            ChatSession.user_id == user.id,
        )
    )
    message = result.scalar_one_or_none()
    if message is None:
        raise HTTPException(status_code=404, detail="Answer not found")
    existing = await db.execute(select(Feedback).where(Feedback.message_id == message.id))
    feedback = existing.scalar_one_or_none()
    if feedback is None:
        feedback = Feedback(message_id=message.id, user_id=user.id, score=payload.score, comment=payload.comment)
        db.add(feedback)
    else:
        feedback.score, feedback.comment = payload.score, payload.comment
    await db.commit()
    return {"message_id": message.id, "score": feedback.score, "comment": feedback.comment}


@router.get("/analytics")
async def analytics(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    documents = await db.scalar(select(func.count(Document.id)).where(Document.user_id == user.id)) or 0
    sessions = await db.scalar(select(func.count(ChatSession.id)).where(ChatSession.user_id == user.id)) or 0
    answers = await db.scalar(
        select(func.count(ChatMessage.id)).join(ChatSession).where(ChatSession.user_id == user.id, ChatMessage.role == "assistant")
    ) or 0
    positive = await db.scalar(select(func.count(Feedback.id)).where(Feedback.user_id == user.id, Feedback.score > 0)) or 0
    negative = await db.scalar(select(func.count(Feedback.id)).where(Feedback.user_id == user.id, Feedback.score < 0)) or 0
    return {"total_documents": documents, "total_chat_sessions": sessions, "total_queries": answers,
            "positive_feedback_count": positive, "negative_feedback_count": negative,
            "feedback_satisfaction_pct": round(positive * 100 / (positive + negative), 1) if positive + negative else 0}
