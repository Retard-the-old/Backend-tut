from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.database import get_db
from app.core.dependencies import require_active_subscription
from app.models.user import User
from app.schemas.chat import ChatSessionResponse, ChatMessageResponse, SendMessageRequest, SendMessageResponse
from app.services.chat_service import send_message, get_sessions, get_session_messages

router = APIRouter(prefix="/chat", tags=["chat"])

@router.post("/messages", response_model=SendMessageResponse)
async def chat(req: SendMessageRequest, user: User = Depends(require_active_subscription), db: AsyncSession = Depends(get_db)):
    return await send_message(user.id, req, db)

@router.get("/sessions", response_model=list[ChatSessionResponse])
async def list_sessions(user: User = Depends(require_active_subscription), db: AsyncSession = Depends(get_db)):
    sessions = await get_sessions(user.id, db)
    return [ChatSessionResponse.model_validate(s) for s in sessions]

@router.get("/sessions/{session_id}/messages", response_model=list[ChatMessageResponse])
async def session_messages(session_id: str, user: User = Depends(require_active_subscription), db: AsyncSession = Depends(get_db)):
    msgs = await get_session_messages(user.id, session_id, db)
    return [ChatMessageResponse.model_validate(m) for m in msgs]
