from __future__ import annotations

from eval.judge import JudgeResult, _extract_json, _normalize_result


def test_extract_json_from_plain_text():
    parsed = _extract_json('{"score": 4, "hit_points": ["a"], "missing_points": [], "hallucination": false, "reason": "ok"}')
    assert parsed is not None
    assert parsed["score"] == 4


def test_extract_json_from_markdown_block():
    parsed = _extract_json('结果如下:\n```json\n{"score": 3, "hit_points": [], "missing_points": ["b"], "hallucination": false, "reason": ""}\n```')
    assert parsed is not None
    assert parsed["score"] == 3


def test_normalize_result_clamps_score():
    result = _normalize_result({"score": 9, "hit_points": [], "missing_points": [], "hallucination": True, "reason": "x"}, raw_text="")
    assert result == JudgeResult(score=5, hit_points=[], missing_points=[], hallucination=True, reason="x")


def test_normalize_result_parse_error():
    result = _normalize_result(None, raw_text="not json")
    assert result.score == 0
    assert "parse_error" in result.reason
