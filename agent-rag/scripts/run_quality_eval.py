#!/usr/bin/env python3
"""Run golden-dataset quality evaluation against assistant or live API."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from eval.client import DEFAULT_RAG_API_URL, check_health
from eval.runner import format_report_summary, run_evaluation, save_report
from rag.logging_config import configure_logging

logger = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run RAG quality evaluation")
    parser.add_argument(
        "--mode",
        choices=("assistant", "api"),
        default="api",
        help="assistant=local CarSafetyWhitepaperAssistant, api=POST /api/chat/stream",
    )
    parser.add_argument(
        "--base-url",
        default=DEFAULT_RAG_API_URL,
        help="RAG API base URL when --mode=api",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Directory for JSON report (default: eval/reports)",
    )
    args = parser.parse_args()

    configure_logging()

    if args.mode == "api" and not check_health(args.base_url):
        logger.error("RAG API health check failed: %s", args.base_url)
        sys.exit(1)

    report = run_evaluation(mode=args.mode, base_url=args.base_url)
    output_dir = Path(args.output_dir) if args.output_dir else None
    report_path = save_report(report, output_dir)
    summary = format_report_summary(report)

    print(summary)
    logger.info("Report saved to %s", report_path)


if __name__ == "__main__":
    main()
