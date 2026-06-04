from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from api.schemas import ChatHistoryResponse, ConversationsResponse, ConversationSummary, HistoryMessage
from db.repository import ConversationRepository
from db.session import get_db

router = APIRouter(prefix="/api/chat", tags=["chat-conversations"])


def _resolve_tenant_id(request: Request) -> str:
    return request.headers.get("X-Tenant-Id") or "default_tenant"


def _message_public_id(message) -> str:
    if message.client_message_id:
        return message.client_message_id
    return str(message.id)


@router.get("/conversations", response_model=ConversationsResponse)
def list_conversations(
    request: Request,
    limit: int = 50,
    offset: int = 0,
) -> ConversationsResponse:
    tenant_id = _resolve_tenant_id(request)
    limit = min(max(limit, 1), 100)
    offset = max(offset, 0)

    with get_db() as session:
        rows = ConversationRepository(session).list_conversations(tenant_id, limit=limit, offset=offset)
        summaries = [
            ConversationSummary(
                thread_id=row.thread_id,
                title=row.title,
                collection_name=row.collection_name,
                message_count=row.message_count,
                updated_at=row.updated_at,
            )
            for row in rows
        ]

    return ConversationsResponse(conversations=summaries)


@router.get("/history", response_model=ChatHistoryResponse)
def chat_history(thread_id: str, request: Request) -> ChatHistoryResponse:
    tenant_id = _resolve_tenant_id(request)

    with get_db() as session:
        conversation, messages = ConversationRepository(session).get_full_history(tenant_id, thread_id)
        if conversation is None:
            raise HTTPException(status_code=404, detail="thread not found")
        return ChatHistoryResponse(
            thread_id=thread_id,
            collection_name=conversation.collection_name,
            messages=[
                HistoryMessage(
                    id=_message_public_id(msg),
                    role=msg.role,
                    content=msg.content,
                    metadata=msg.metadata_json,
                )
                for msg in messages
            ],
        )


@router.delete("/conversations/{thread_id}")
def delete_conversation(thread_id: str, request: Request) -> dict[str, str]:
    tenant_id = _resolve_tenant_id(request)

    with get_db() as session:
        deleted = ConversationRepository(session).delete_conversation(tenant_id, thread_id)

    if not deleted:
        raise HTTPException(status_code=404, detail="thread not found")
    return {"status": "ok"}
