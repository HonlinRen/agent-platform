from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from api.schemas import ChatFeedbackRequest
from db.repository import ConversationRepository
from db.session import get_db
from rag.telemetry import record_feedback

router = APIRouter(prefix="/api/chat", tags=["chat-feedback"])


@router.post("/feedback")
def chat_feedback(body: ChatFeedbackRequest, request: Request) -> dict[str, str]:
    tenant_id = request.headers.get("X-Tenant-Id") or "default_tenant"

    try:
        with get_db() as session:
            ConversationRepository(session).save_feedback(
                tenant_id=tenant_id,
                thread_id=body.thread_id,
                message_id=body.message_id,
                rating=body.rating,
                comment=body.comment,
            )
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"feedback store unavailable: {exc}") from exc

    record_feedback(body.rating)
    return {"status": "ok"}
