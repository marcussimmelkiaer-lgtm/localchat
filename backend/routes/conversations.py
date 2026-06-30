from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, Request, Response

from .. import store
from ..schemas import (
    ConversationDetail,
    ConversationOut,
    CreateConversation,
    RenameConversation,
)

router = APIRouter(prefix="/api/conversations", tags=["conversations"])


@router.get("", response_model=list[ConversationOut])
def list_conversations():
    return store.list_conversations()


@router.post("", response_model=ConversationOut)
def create_conversation(body: CreateConversation):
    cid = uuid.uuid4().hex
    return store.create_conversation(cid, body.title or "")


@router.get("/{conv_id}", response_model=ConversationDetail)
def get_conversation(conv_id: str):
    conv = store.get_conversation(conv_id)
    if not conv:
        raise HTTPException(status_code=404, detail="conversation not found")
    conv["messages"] = store.get_messages(conv_id)
    return conv


@router.patch("/{conv_id}", response_model=ConversationOut)
def rename_conversation(conv_id: str, body: RenameConversation):
    if not store.get_conversation(conv_id):
        raise HTTPException(status_code=404, detail="conversation not found")
    store.rename_conversation(conv_id, body.title)
    return store.get_conversation(conv_id)


@router.delete("/{conv_id}", status_code=204)
def delete_conversation(conv_id: str, request: Request):
    store.delete_conversation(conv_id)
    try:
        request.app.state.engine.evict(conv_id)
    except Exception:  # noqa: BLE001
        pass
    return Response(status_code=204)
