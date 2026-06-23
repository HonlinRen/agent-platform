from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from sqlalchemy import delete, desc, func, select
from sqlalchemy.orm import Session

from db.models import ChatFeedback, ChatMessage, Conversation, TenantProfile
from rag.memory.types import MemoryContextData

logger = logging.getLogger(__name__)

TITLE_MAX_LEN = 100


class ConversationRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def _get_or_create_conversation(
        self,
        tenant_id: str,
        thread_id: str,
        collection_name: str | None,
        user_message: str,
    ) -> Conversation:
        stmt = (
            select(Conversation)
            .where(Conversation.tenant_id == tenant_id, Conversation.thread_id == thread_id)
            .with_for_update()
        )
        conversation = self._session.scalar(stmt)
        if conversation is not None:
            if collection_name and not conversation.collection_name:
                conversation.collection_name = collection_name
            return conversation

        conversation = Conversation(
            tenant_id=tenant_id,
            thread_id=thread_id,
            collection_name=collection_name,
            title=user_message[:TITLE_MAX_LEN],
            message_count=0,
        )
        self._session.add(conversation)
        self._session.flush()
        return conversation

    def _next_sequence(self, conversation_id: int) -> int:
        max_seq = self._session.scalar(
            select(func.max(ChatMessage.sequence)).where(ChatMessage.conversation_id == conversation_id)
        )
        return (max_seq or 0) + 1

    def save_turn(
        self,
        tenant_id: str,
        thread_id: str,
        collection_name: str | None,
        user_message: str,
        assistant_message: str,
        metadata: dict[str, Any] | None = None,
        user_message_id: str | None = None,
        assistant_message_id: str | None = None,
    ) -> None:
        conversation = self._get_or_create_conversation(tenant_id, thread_id, collection_name, user_message)
        seq = self._next_sequence(conversation.id)

        self._session.add(
            ChatMessage(
                conversation_id=conversation.id,
                client_message_id=user_message_id,
                role="user",
                content=user_message,
                sequence=seq,
            )
        )
        self._session.add(
            ChatMessage(
                conversation_id=conversation.id,
                client_message_id=assistant_message_id,
                role="assistant",
                content=assistant_message,
                sequence=seq + 1,
                metadata_json=metadata,
            )
        )
        conversation.message_count += 2
        conversation.updated_at = datetime.now()

    def load_recent_messages(
        self,
        tenant_id: str,
        thread_id: str,
        limit: int,
    ) -> list[dict[str, str]]:
        conversation = self._session.scalar(
            select(Conversation).where(
                Conversation.tenant_id == tenant_id,
                Conversation.thread_id == thread_id,
            )
        )
        if conversation is None:
            return []

        rows = self._session.scalars(
            select(ChatMessage)
            .where(ChatMessage.conversation_id == conversation.id)
            .order_by(desc(ChatMessage.sequence))
            .limit(limit)
        ).all()
        rows.reverse()
        return [{"role": row.role, "content": row.content} for row in rows]

    def load_memory_context(
        self,
        tenant_id: str,
        thread_id: str,
        *,
        limit: int,
    ) -> MemoryContextData:
        conversation = self._session.scalar(
            select(Conversation).where(
                Conversation.tenant_id == tenant_id,
                Conversation.thread_id == thread_id,
            )
        )
        tenant_profile = self._session.scalar(
            select(TenantProfile).where(TenantProfile.tenant_id == tenant_id)
        )
        if conversation is None:
            return MemoryContextData(
                conversation_id=None,
                message_count=0,
                summary=None,
                summary_up_to_sequence=0,
                recent_messages=[],
                tenant_profile_summary=tenant_profile.profile_summary if tenant_profile else None,
                tenant_profile_source=tenant_profile.source if tenant_profile else None,
            )

        rows = self._session.scalars(
            select(ChatMessage)
            .where(ChatMessage.conversation_id == conversation.id)
            .order_by(desc(ChatMessage.sequence))
            .limit(limit)
        ).all()
        rows.reverse()
        recent = [{"role": row.role, "content": row.content} for row in rows]
        return MemoryContextData(
            conversation_id=conversation.id,
            message_count=conversation.message_count,
            summary=conversation.summary,
            summary_up_to_sequence=conversation.summary_up_to_sequence or 0,
            recent_messages=recent,
            tenant_profile_summary=tenant_profile.profile_summary if tenant_profile else None,
            tenant_profile_source=tenant_profile.source if tenant_profile else None,
        )

    def get_messages_for_summary(
        self,
        tenant_id: str,
        thread_id: str,
        *,
        after_sequence: int,
        before_sequence: int,
    ) -> list[ChatMessage]:
        conversation = self._session.scalar(
            select(Conversation).where(
                Conversation.tenant_id == tenant_id,
                Conversation.thread_id == thread_id,
            )
        )
        if conversation is None:
            return []
        return list(
            self._session.scalars(
                select(ChatMessage)
                .where(
                    ChatMessage.conversation_id == conversation.id,
                    ChatMessage.sequence > after_sequence,
                    ChatMessage.sequence <= before_sequence,
                )
                .order_by(ChatMessage.sequence)
            ).all()
        )

    def get_max_message_sequence(self, tenant_id: str, thread_id: str) -> int:
        conversation = self._session.scalar(
            select(Conversation).where(
                Conversation.tenant_id == tenant_id,
                Conversation.thread_id == thread_id,
            )
        )
        if conversation is None:
            return 0
        max_seq = self._session.scalar(
            select(func.max(ChatMessage.sequence)).where(ChatMessage.conversation_id == conversation.id)
        )
        return max_seq or 0

    def update_conversation_summary(
        self,
        tenant_id: str,
        thread_id: str,
        summary: str,
        up_to_sequence: int,
    ) -> None:
        conversation = self._session.scalar(
            select(Conversation).where(
                Conversation.tenant_id == tenant_id,
                Conversation.thread_id == thread_id,
            )
        )
        if conversation is None:
            return
        conversation.summary = summary
        conversation.summary_up_to_sequence = up_to_sequence
        conversation.summary_updated_at = datetime.now()

    def get_conversation(
        self,
        tenant_id: str,
        thread_id: str,
    ) -> Conversation | None:
        return self._session.scalar(
            select(Conversation).where(
                Conversation.tenant_id == tenant_id,
                Conversation.thread_id == thread_id,
            )
        )

    def get_tenant_profile(self, tenant_id: str) -> TenantProfile | None:
        return self._session.scalar(select(TenantProfile).where(TenantProfile.tenant_id == tenant_id))

    def upsert_tenant_profile(
        self,
        tenant_id: str,
        profile_json: dict[str, Any],
        profile_summary: str,
        *,
        source: str = "auto",
    ) -> None:
        row = self.get_tenant_profile(tenant_id)
        if row is None:
            self._session.add(
                TenantProfile(
                    tenant_id=tenant_id,
                    profile_json=profile_json,
                    profile_summary=profile_summary,
                    source=source,
                )
            )
            return
        if row.source == "manual" and source == "auto":
            merged = dict(row.profile_json or {})
            for key, value in profile_json.items():
                if key not in merged or not merged.get(key):
                    merged[key] = value
            row.profile_json = merged
            if not row.profile_summary:
                row.profile_summary = profile_summary
            return
        row.profile_json = profile_json
        row.profile_summary = profile_summary
        row.source = source
        row.updated_at = datetime.now()

    def count_tenant_messages(self, tenant_id: str) -> int:
        total = self._session.scalar(
            select(func.coalesce(func.sum(Conversation.message_count), 0)).where(
                Conversation.tenant_id == tenant_id
            )
        )
        return int(total or 0)

    def get_full_history(
        self,
        tenant_id: str,
        thread_id: str,
    ) -> tuple[Conversation | None, list[ChatMessage]]:
        conversation = self._session.scalar(
            select(Conversation).where(
                Conversation.tenant_id == tenant_id,
                Conversation.thread_id == thread_id,
            )
        )
        if conversation is None:
            return None, []

        messages = list(
            self._session.scalars(
                select(ChatMessage)
                .where(ChatMessage.conversation_id == conversation.id)
                .order_by(ChatMessage.sequence)
            ).all()
        )
        return conversation, messages

    def list_conversations(
        self,
        tenant_id: str,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Conversation]:
        return list(
            self._session.scalars(
                select(Conversation)
                .where(Conversation.tenant_id == tenant_id)
                .order_by(desc(Conversation.updated_at))
                .limit(limit)
                .offset(offset)
            ).all()
        )

    def delete_conversation(self, tenant_id: str, thread_id: str) -> bool:
        conversation = self._session.scalar(
            select(Conversation).where(
                Conversation.tenant_id == tenant_id,
                Conversation.thread_id == thread_id,
            )
        )
        if conversation is None:
            return False
        self._session.delete(conversation)
        return True

    def save_feedback(
        self,
        tenant_id: str,
        thread_id: str,
        message_id: str,
        rating: str,
        comment: str = "",
    ) -> None:
        self._session.add(
            ChatFeedback(
                tenant_id=tenant_id,
                thread_id=thread_id,
                message_id=message_id,
                rating=rating,
                comment=comment or None,
            )
        )


def save_turn_best_effort(**kwargs: Any) -> None:
    try:
        from db.session import get_db

        with get_db() as session:
            ConversationRepository(session).save_turn(**kwargs)
    except Exception:
        logger.exception("Failed to persist chat turn to MySQL")
