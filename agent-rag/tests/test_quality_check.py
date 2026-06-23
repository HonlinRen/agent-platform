from __future__ import annotations

import logging
import os

import pytest

from eval.client import DEFAULT_RAG_API_URL, check_health

logger = logging.getLogger(__name__)

pytestmark = pytest.mark.skipif(
    os.getenv("EVAL_INTEGRATION") != "1",
    reason="Set EVAL_INTEGRATION=1 to run live RAG quality eval",
)


def _require_integration_env() -> str:
    if not (os.environ.get("DASHSCOPE_API_KEY") or os.environ.get("API_KEY")):
        pytest.skip("DASHSCOPE_API_KEY is required for AI Judge scoring")

    base_url = os.environ.get("RAG_API_URL", DEFAULT_RAG_API_URL)
    if not check_health(base_url):
        pytest.skip(f"RAG API is not reachable: {base_url}")
    return base_url


def test_quality_eval_produces_report(caplog):
    from eval.runner import format_report_summary, run_evaluation, save_report

    caplog.set_level(logging.INFO)
    base_url = _require_integration_env()

    report = run_evaluation(mode="api", base_url=base_url)
    report_path = save_report(report)
    summary = format_report_summary(report)

    logger.info("Quality eval report saved to %s", report_path)
    logger.info("\n%s", summary)

    assert report.total > 0
    assert len(report.cases) == report.total
    assert report_path.exists()
