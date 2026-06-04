# -*- coding: utf-8 -*-
from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from submit_doc_parser_job_advance import submit_doc_parser_job
from get_doc_result import get_doc_result, query_parser_status
from ingest_chroma import load_json_and_ingest_chroma

logger = logging.getLogger(__name__)


def wait_for_result(
    pdf_name: str,
    task_id: str,
    *,
    interval_seconds: int = 5,
    max_attempts: int = 60,
    layout_step_size: int = 100,
) -> Path:
    result_path = PROJECT_ROOT / "doc_result" / f"{Path(pdf_name).stem}.json"

    for attempt in range(1, max_attempts + 1):
        status_data = query_parser_status(task_id)
        status = str(status_data.get("Status") or "").lower()
        logger.info(
            "poll %d/%d status=%s processing=%s",
            attempt,
            max_attempts,
            status_data.get("Status"),
            status_data.get("Processing"),
        )

        if status == "success":
            result_path = get_doc_result(
                pdf_name,
                task_id,
                layout_step_size=layout_step_size,
            )
            return result_path

        if status == "fail":
            raise RuntimeError(f"DocParser job failed: {task_id} status={status_data}")

        if attempt < max_attempts:
            time.sleep(interval_seconds)

    raise TimeoutError(
        f"DocParser result is still not completed after {max_attempts} attempts: {task_id}"
    )


def main() -> None:
    from rag.logging_config import configure_logging

    configure_logging()
    parser = argparse.ArgumentParser(
        description="Submit DocParser job (大模型版), fetch result, and ingest into Chroma"
    )
    parser.add_argument("--file-name", default="VSOC_32.pdf")
    parser.add_argument("--file-name-extension", default="pdf")
    parser.add_argument("--collection-name", default=None, help="Chroma 集合名称（默认读取环境变量）")
    parser.add_argument("--interval-seconds", type=int, default=5)
    parser.add_argument("--max-attempts", type=int, default=60)
    parser.add_argument("--layout-step-size", type=int, default=100)
    args = parser.parse_args()

    task_id = submit_doc_parser_job(args.file_name, args.file_name_extension)
    logger.info("Submitted DocParser job task_id=%s", task_id)

    time.sleep(args.interval_seconds)
    result_path = wait_for_result(
        args.file_name,
        task_id,
        interval_seconds=args.interval_seconds,
        max_attempts=args.max_attempts,
        layout_step_size=args.layout_step_size,
    )
    logger.info("DocParser result saved to %s", result_path)

    time.sleep(args.interval_seconds)
    load_json_and_ingest_chroma(result_path, collection_name=args.collection_name)


if __name__ == "__main__":
    main()
