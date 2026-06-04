from __future__ import annotations

import os

KNOWLEDGE_BASES: dict[str, str] = {
    "white_paper_iot": "汽车安全",
    "semiconductor": "半导体",
}

DOMAIN_HINTS: dict[str, str] = {
    "white_paper_iot": "汽车安全白皮书",
    "semiconductor": "半导体行业文档",
}

DEFAULT_COLLECTION = os.environ.get("CHROMA_COLLECTION_NAME", "white_paper_iot")


def validate_collection_name(name: str | None) -> str:
    resolved = (name or "").strip() or DEFAULT_COLLECTION
    if resolved not in KNOWLEDGE_BASES:
        allowed = "、".join(f"{label}({key})" for key, label in KNOWLEDGE_BASES.items())
        raise ValueError(f"无效的知识库，请选择：{allowed}")
    return resolved


def get_domain_hint(collection_name: str) -> str:
    return DOMAIN_HINTS.get(collection_name, "知识库文档")


def get_label(collection_name: str) -> str:
    return KNOWLEDGE_BASES.get(collection_name, collection_name)


def list_knowledge_bases() -> list[dict[str, str]]:
    return [{"id": key, "label": label} for key, label in KNOWLEDGE_BASES.items()]
