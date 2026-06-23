"""Qwen AI Judge for RAG answer quality scoring."""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from langchain_openai import ChatOpenAI

logger = logging.getLogger(__name__)

DASHSCOPE_API_KEY = os.environ.get("DASHSCOPE_API_KEY") or os.environ.get("API_KEY")
JUDGE_MODEL = os.environ.get("EVAL_JUDGE_MODEL") or os.environ.get("DASHSCOPE_LLM_MODEL", "qwen-plus")
DASHSCOPE_BASE_URL = os.environ.get(
    "DASHSCOPE_BASE_URL",
    "https://dashscope.aliyuncs.com/compatible-mode/v1",
)

JUDGE_PROMPT = """你是一个严格的 RAG 知识库问答评测专家。

请根据【问题】、【标准答案】、【关键评分点】评估【模型回答】。

评分规则：
5 分：完全正确，覆盖全部关键点，无幻觉。
4 分：基本正确，覆盖大部分关键点，仅有轻微遗漏。
3 分：方向正确，但遗漏较多关键点。
2 分：只包含少量相关内容，不能完整回答问题。
1 分：大部分错误或答非所问。
0 分：完全错误，或出现严重幻觉。

评估要求：
1. 不要求模型回答和标准答案逐字一致，只看语义是否一致。
2. 如果回答覆盖了关键评分点，应计为命中。
3. 如果回答编造了标准答案或参考资料中没有的信息，应标记为 hallucination=true。
4. 如果知识库没有答案，而模型强行编造，也应严重扣分。
5. 请输出 JSON，不要输出额外解释。

【问题】
{question}

【标准答案】
{gold_answer}

【关键评分点】
{must_have_points}

【模型回答】
{model_answer}

请输出：
{{
  "score": 0,
  "hit_points": [],
  "missing_points": [],
  "hallucination": false,
  "reason": ""
}}"""


def _llm_output_to_text(output: Any) -> str:
    if isinstance(output, str):
        return output.strip()
    content = getattr(output, "content", None)
    if isinstance(content, str):
        return content.strip()
    return str(output).strip()


@dataclass
class JudgeResult:
    score: int
    hit_points: list[str]
    missing_points: list[str]
    hallucination: bool
    reason: str

    def to_dict(self) -> dict:
        return asdict(self)


def _build_judge_llm() -> ChatOpenAI:
    from langchain_openai import ChatOpenAI

    if not DASHSCOPE_API_KEY:
        raise RuntimeError("Missing environment variable: DASHSCOPE_API_KEY or API_KEY")
    return ChatOpenAI(
        model=JUDGE_MODEL,
        api_key=DASHSCOPE_API_KEY,
        base_url=DASHSCOPE_BASE_URL,
        temperature=0.0,
        streaming=False,
    )


def _format_must_have_points(points: list[str]) -> str:
    return "\n".join(f"- {point}" for point in points)


def _extract_json(text: str) -> dict | None:
    text = text.strip()
    if not text:
        return None
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass

    match = re.search(r"\{[\s\S]*\}", text)
    if not match:
        return None
    try:
        parsed = json.loads(match.group(0))
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        return None
    return None


def _normalize_result(data: dict | None, *, raw_text: str) -> JudgeResult:
    if not data:
        return JudgeResult(
            score=0,
            hit_points=[],
            missing_points=[],
            hallucination=False,
            reason=f"parse_error: {raw_text[:200]}",
        )

    score = data.get("score", 0)
    try:
        score = max(0, min(5, int(score)))
    except (TypeError, ValueError):
        score = 0

    hit_points = data.get("hit_points") or []
    missing_points = data.get("missing_points") or []
    if not isinstance(hit_points, list):
        hit_points = [str(hit_points)]
    if not isinstance(missing_points, list):
        missing_points = [str(missing_points)]

    hallucination = bool(data.get("hallucination", False))
    reason = str(data.get("reason") or "").strip()
    return JudgeResult(
        score=score,
        hit_points=[str(item) for item in hit_points],
        missing_points=[str(item) for item in missing_points],
        hallucination=hallucination,
        reason=reason,
    )


def score_answer(
    question: str,
    gold_answer: str,
    must_have_points: list[str],
    model_answer: str,
    *,
    llm: ChatOpenAI | None = None,
) -> JudgeResult:
    judge_llm = llm or _build_judge_llm()
    prompt = JUDGE_PROMPT.format(
        question=question,
        gold_answer=gold_answer,
        must_have_points=_format_must_have_points(must_have_points),
        model_answer=model_answer,
    )
    response = judge_llm.invoke(prompt)
    raw_text = _llm_output_to_text(response)
    parsed = _extract_json(raw_text)
    result = _normalize_result(parsed, raw_text=raw_text)
    logger.info(
        "judge score=%s hallucination=%s reason=%s",
        result.score,
        result.hallucination,
        result.reason[:120],
    )
    return result
