from __future__ import annotations

import json
import logging
import os
from typing import Any

from langchain_core.prompts import PromptTemplate

from rag.memory.formatting import format_memory_placeholder, format_messages_text
from rag.llm_timing import timed_llm_invoke
from rag.telemetry import span

logger = logging.getLogger(__name__)

TENANT_PROFILE_ENABLED = os.environ.get("TENANT_PROFILE_ENABLED", "true").lower() in {"1", "true", "yes"}
TENANT_PROFILE_UPDATE_INTERVAL = int(os.environ.get("TENANT_PROFILE_UPDATE_INTERVAL", "6"))
TENANT_PROFILE_BOOTSTRAP_MESSAGES = int(os.environ.get("TENANT_PROFILE_BOOTSTRAP_MESSAGES", "4"))

DEFAULT_PROFILE: dict[str, Any] = {
    "focus_domains": [],
    "preferred_answer_style": "",
    "common_systems": [],
    "notes": "",
}

EXTRACT_PROMPT = PromptTemplate(
    input_variables=["old_profile", "conversation_summary", "recent_messages"],
    template=(
        "你是企业知识库租户画像提取助手。请从会话信息中提取租户级业务背景，输出 JSON。\n\n"
        "要求：\n"
        "1. 只提取业务上下文：关注领域、常用系统、回答风格偏好\n"
        "2. 不要提取个人身份信息、姓名、手机号等隐私\n"
        "3. 字段固定为：focus_domains(数组), preferred_answer_style(字符串), "
        "common_systems(数组), notes(字符串)\n"
        "4. 只输出 JSON，不要 markdown\n\n"
        "【旧画像 JSON】\n{old_profile}\n\n"
        "【会话摘要】\n{conversation_summary}\n\n"
        "【最近对话】\n{recent_messages}\n\n"
        "JSON："
    ),
)


def merge_profiles(old: dict[str, Any], new: dict[str, Any]) -> dict[str, Any]:
    merged = dict(DEFAULT_PROFILE)
    merged.update(old or {})
    for key in DEFAULT_PROFILE:
        if key not in new:
            continue
        value = new[key]
        if key in {"focus_domains", "common_systems"} and isinstance(value, list):
            existing = merged.get(key) or []
            if not isinstance(existing, list):
                existing = [existing]
            combined = list(dict.fromkeys([*existing, *value]))
            merged[key] = combined[:10]
        elif isinstance(value, str) and value.strip():
            if key == "notes" and merged.get("notes"):
                merged[key] = f"{merged['notes']}；{value.strip()}"[:200]
            else:
                merged[key] = value.strip()
    return merged


def profile_to_summary(profile: dict[str, Any]) -> str:
    parts: list[str] = []
    domains = profile.get("focus_domains") or []
    if domains:
        parts.append(f"关注领域：{', '.join(str(d) for d in domains[:5])}")
    style = profile.get("preferred_answer_style") or ""
    if style:
        parts.append(f"回答风格偏好：{style}")
    systems = profile.get("common_systems") or []
    if systems:
        parts.append(f"常用系统：{', '.join(str(s) for s in systems[:5])}")
    notes = profile.get("notes") or ""
    if notes:
        parts.append(str(notes)[:200])
    return "；".join(parts)[:200]


def _should_update_tenant_profile(total_messages: int, profile_row) -> bool:
    if total_messages <= 0:
        return False
    if profile_row is None and total_messages >= TENANT_PROFILE_BOOTSTRAP_MESSAGES:
        return True
    return total_messages % TENANT_PROFILE_UPDATE_INTERVAL == 0


def _parse_profile_json(text: str) -> dict[str, Any]:
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        text = "\n".join(line for line in lines if not line.strip().startswith("```")).strip()
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        logger.warning("Failed to parse tenant profile JSON: %s", text[:200])
    return {}


def update_tenant_profile_auto(
    assistant,
    tenant_id: str,
    thread_id: str,
) -> bool:
    if not TENANT_PROFILE_ENABLED:
        return False

    from db.repository import ConversationRepository
    from db.session import get_db
    from rag.memory.types import get_window_size

    with get_db() as session:
        repo = ConversationRepository(session)
        total_messages = repo.count_tenant_messages(tenant_id)
        profile_row = repo.get_tenant_profile(tenant_id)
        if not _should_update_tenant_profile(total_messages, profile_row):
            return False

        if profile_row and profile_row.source == "manual":
            return False

        data = repo.load_memory_context(tenant_id, thread_id, limit=get_window_size() * 2)
        old_profile = profile_row.profile_json if profile_row else DEFAULT_PROFILE
        chain = EXTRACT_PROMPT | assistant.router_llm
        with span("rag.llm.invoke", {"rag.operation": "tenant_profile"}):
            result = timed_llm_invoke(
                "tenant_profile",
                lambda: chain.invoke(
                    {
                        "old_profile": json.dumps(old_profile, ensure_ascii=False),
                        "conversation_summary": format_memory_placeholder(data.summary or ""),
                        "recent_messages": format_messages_text(data.recent_messages),
                    }
                ),
                phase="post_turn",
            )
        from rag.assistant import llm_output_to_text

        extracted = _parse_profile_json(llm_output_to_text(result))
        if not extracted:
            return False
        merged = merge_profiles(old_profile if isinstance(old_profile, dict) else DEFAULT_PROFILE, extracted)
        summary = profile_to_summary(merged)
        repo.upsert_tenant_profile(tenant_id, merged, summary, source="auto")
        logger.info("Updated tenant profile tenant=%s", tenant_id)
        return True


def maybe_update_tenant_profile_best_effort(assistant, tenant_id: str, thread_id: str) -> None:
    try:
        update_tenant_profile_auto(assistant, tenant_id, thread_id)
    except Exception:
        logger.exception("Failed to update tenant profile")
