from __future__ import annotations

from rag.memory.formatting import build_memory_context, format_memory_placeholder, format_messages_text
from rag.memory.triggers import should_update_summary
from rag.memory.tenant_profile import merge_profiles, profile_to_summary
from rag.memory.tokens import estimate_messages_tokens, estimate_tokens
from rag.memory.types import MemoryContext, MemoryContextData


def test_format_messages_text_includes_assistant():
    messages = [
        {"role": "user", "content": "Redis 怎么部署？"},
        {"role": "assistant", "content": "建议一主两从。"},
        {"role": "user", "content": "高可用呢？"},
    ]
    text = format_messages_text(messages)
    assert "Human: Redis 怎么部署？" in text
    assert "AI: 建议一主两从。" in text
    assert "Human: 高可用呢？" in text


def test_format_memory_placeholder():
    assert format_memory_placeholder("") == "无"
    assert format_memory_placeholder("  摘要  ") == "摘要"


def test_build_memory_context():
    data = MemoryContextData(
        conversation_id=1,
        message_count=4,
        summary="围绕 Redis 高可用",
        summary_up_to_sequence=2,
        recent_messages=[{"role": "user", "content": "风险？"}],
        tenant_profile_summary="关注 Redis",
        tenant_profile_source="auto",
    )
    ctx = build_memory_context(data)
    assert ctx.conversation_summary == "围绕 Redis 高可用"
    assert ctx.tenant_profile_summary == "关注 Redis"
    assert len(ctx.recent_messages) == 1
    assert ctx.to_metadata()["has_summary"] is True


def test_should_update_summary_by_rounds():
    assert should_update_summary(18, []) is False
    assert should_update_summary(22, []) is True


def test_should_update_summary_by_tokens():
    messages = [{"role": "user", "content": "x" * 12000}]
    assert should_update_summary(4, messages) is True


def test_estimate_tokens():
    assert estimate_tokens("") == 0
    assert estimate_messages_tokens([{"role": "user", "content": "abcd"}]) >= 1


def test_merge_profiles_deduplicates_lists():
    merged = merge_profiles(
        {"focus_domains": ["Redis"], "preferred_answer_style": "", "common_systems": [], "notes": ""},
        {"focus_domains": ["Redis", "MySQL"], "preferred_answer_style": "concise", "common_systems": [], "notes": ""},
    )
    assert merged["focus_domains"] == ["Redis", "MySQL"]
    assert merged["preferred_answer_style"] == "concise"


def test_profile_to_summary():
    summary = profile_to_summary(
        {
            "focus_domains": ["Redis"],
            "preferred_answer_style": "concise",
            "common_systems": ["Chroma"],
            "notes": "常问部署",
        }
    )
    assert "Redis" in summary
    assert "concise" in summary


def test_memory_context_metadata():
    ctx = MemoryContext(
        recent_messages=[{"role": "user", "content": "hi"}],
        recent_messages_text="Human: hi",
        conversation_summary="",
        tenant_profile_summary="",
        window_size=5,
    )
    meta = ctx.to_metadata()
    assert meta["window_size"] == 5
    assert meta["recent_message_count"] == 1
    assert meta["has_summary"] is False
