from __future__ import annotations

from eval import GoldenQuestion, load_golden_dataset


def test_load_golden_dataset():
    items = load_golden_dataset()
    assert len(items) == 8
    assert all(isinstance(item, GoldenQuestion) for item in items)
    assert all(item.collection_name == "semiconductor" for item in items)
    assert all(item.must_have_points for item in items)


def test_golden_question_from_dict():
    item = GoldenQuestion.from_dict(
        {
            "question": "q",
            "gold_answer": "a",
            "reference_doc": "doc.pdf",
            "must_have_points": ["p1"],
            "collection_name": "semiconductor",
        }
    )
    assert item.question == "q"
