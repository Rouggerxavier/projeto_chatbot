from fastapi import APIRouter
from pydantic import BaseModel as PydanticBaseModel
from typing import Optional
from uuid import uuid4

from app.flows import handle_message

router = APIRouter()

class ChatRequest(PydanticBaseModel):
    message: str
    user_id: Optional[str] = None

class ChatResponse(PydanticBaseModel):
    reply: str
    needs_human: bool = False
    session_id: str

@router.post("/chat", response_model=ChatResponse)
async def chat_endpoint(body: ChatRequest):
    print("DEBUG user_id =", body.user_id, "message =", body.message)
    message = body.message or ""
    session_id = (body.user_id or "").strip() or uuid4().hex

    reply, needs_human = handle_message(message=message, session_id=session_id)

    return ChatResponse(reply=reply, needs_human=needs_human, session_id=session_id)
