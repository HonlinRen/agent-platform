from __future__ import annotations

import os

RETRIEVAL_MIN_SCORE = float(os.environ.get("RETRIEVAL_MIN_SCORE", "0.15"))

REJECT_MESSAGE = (
    "白皮书上下文中未找到充分依据，无法给出可靠回答。"
    "请尝试换一种问法，或补充更具体的章节、术语或页码信息。"
)

CLARIFY_MESSAGE = (
    "检索到的内容与问题相关度较低，请补充更具体的信息"
    "（例如章节名称、页码或关键术语），以便更准确检索。"
)


def max_rerank_score(ranked: list[dict]) -> float | None:
    scores = [item.get("rerank_score") for item in ranked if isinstance(item.get("rerank_score"), (int, float))]
    return max(scores) if scores else None


def reject_reason(ranked: list[dict]) -> str:
    if not ranked:
        return "no_results"
    best = max_rerank_score(ranked)
    if best is not None and best < RETRIEVAL_MIN_SCORE:
        return "low_score"
    return "unknown"


def should_reject(ranked: list[dict]) -> tuple[bool, str]:
    if not ranked:
        return True, REJECT_MESSAGE
    best = max_rerank_score(ranked)
    if best is not None and best < RETRIEVAL_MIN_SCORE:
        return True, CLARIFY_MESSAGE
    return False, ""
