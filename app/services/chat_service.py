from __future__ import annotations
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from fastapi import HTTPException, status
from app.models.chat import ChatSession, ChatMessage
from app.models.course import Lesson
from app.clients.claude_ai import claude_client
from app.schemas.chat import SendMessageRequest, SendMessageResponse, ChatMessageResponse

async def send_message(user_id: str, req: SendMessageRequest, db: AsyncSession) -> SendMessageResponse:
    if req.session_id:
        sess = (await db.execute(
            select(ChatSession).where(ChatSession.id == req.session_id, ChatSession.user_id == user_id)
        )).scalar_one_or_none()
        if sess is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat session not found")
        session = sess
    else:
        session = ChatSession(
            user_id=user_id, course_id=req.course_id, lesson_id=req.lesson_id,
            title=req.content[:60] + ("..." if len(req.content) > 60 else ""),
        )
        db.add(session)
        await db.flush()

    user_msg = ChatMessage(session_id=session.id, role="user", content=req.content)
    db.add(user_msg)
    await db.flush()

    history = [{"role": m.role, "content": m.content} for m in (await db.execute(
        select(ChatMessage).where(ChatMessage.session_id == session.id).order_by(ChatMessage.created_at)
    )).scalars().all()]

    lesson_context = None
    lid = session.lesson_id or req.lesson_id
    if lid:
        lesson = (await db.execute(select(Lesson).where(Lesson.id == lid))).scalar_one_or_none()
        if lesson and lesson.content_md:
            lesson_context = f"Lesson: {lesson.title}\n\n{lesson.content_md[:3000]}"

    response = await claude_client.chat(messages=history, lesson_context=lesson_context)

    assistant_msg = ChatMessage(
        session_id=session.id, role="assistant", content=response["content"],
        tokens_used=response["usage"].get("output_tokens", 0),
    )
    db.add(assistant_msg)
    session.message_count += 2
    await db.flush()

    return SendMessageResponse(
        session_id=session.id,
        user_message=ChatMessageResponse.model_validate(user_msg),
        assistant_message=ChatMessageResponse.model_validate(assistant_msg),
    )

async def get_sessions(user_id: str, db: AsyncSession) -> list[ChatSession]:
    return list((await db.execute(
        select(ChatSession).where(ChatSession.user_id == user_id).order_by(ChatSession.updated_at.desc()).limit(50)
    )).scalars().all())

async def get_session_messages(user_id: str, session_id: str, db: AsyncSession) -> list[ChatMessage]:
    sess = (await db.execute(
        select(ChatSession).where(ChatSession.id == session_id, ChatSession.user_id == user_id)
    )).scalar_one_or_none()
    if sess is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    return list((await db.execute(
        select(ChatMessage).where(ChatMessage.session_id == session_id).order_by(ChatMessage.created_at)
    )).scalars().all())
