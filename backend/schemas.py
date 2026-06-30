from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class Stats(BaseModel):
    tokens: int = 0
    seconds: float = 0.0
    tokens_per_second: float = 0.0
    ttft_ms: float = 0.0


class AttachmentIn(BaseModel):
    """One uploaded file, base64-encoded inline in the chat request body."""
    name: str
    mime: str = ""
    data_b64: str


class AttachmentMeta(BaseModel):
    """Lightweight attachment metadata returned to the UI (no bytes/text)."""
    name: str
    mime: str = ""
    size: int = 0


class MessageOut(BaseModel):
    id: str
    role: str
    content: str
    status: str = "done"
    stats: Optional[Stats] = None
    error: Optional[str] = None
    attachments: list[AttachmentMeta] = []
    created_at: str


class ConversationOut(BaseModel):
    id: str
    title: str
    created_at: str
    updated_at: str


class ConversationDetail(ConversationOut):
    messages: list[MessageOut] = []


class CreateConversation(BaseModel):
    title: Optional[str] = None


class RenameConversation(BaseModel):
    title: str


class ChatStreamRequest(BaseModel):
    conversation_id: str
    content: str
    # Client-supplied ids so the frontend's optimistic messages and the
    # persisted rows share the same id (no reconciliation on reload).
    user_message_id: str
    assistant_message_id: str
    attachments: list[AttachmentIn] = []


class RegenerateRequest(BaseModel):
    conversation_id: str
    assistant_message_id: str


class StopRequest(BaseModel):
    conversation_id: str
