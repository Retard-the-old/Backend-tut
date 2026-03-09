from __future__ import annotations
from pydantic import BaseModel
from datetime import datetime

class ChatSessionResponse(BaseModel):
    id: str
    title: str
    course_id: str | None
    lesson_id: str | None
    message_count: int
    created_at: datetime
    updated_at: datetime
    model_config = {"from_attributes": True}

class ChatMessageResponse(BaseModel):
    id: str
    role: str
    content: str
    tokens_used: int
    created_at: datetime
    model_config = {"from_attributes": True}

class SendMessageRequest(BaseModel):
    content: str
    session_id: str | None = None
    course_id: str | None = None
    lesson_id: str | None = None

class SendMessageResponse(BaseModel):
    session_id: str
    user_message: ChatMessageResponse
    assistant_message: ChatMessageResponse
