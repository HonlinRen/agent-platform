# -*- coding: utf-8 -*-
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from pathlib import Path

from alibabacloud_docmind_api20220711 import models as docmind_api20220711_models
from alibabacloud_tea_util import models as util_models
from alibabacloud_tea_util.client import Client as UtilClient

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from docmind_client import create_client
from get_doc_result import (
    DEFAULT_LAYOUT_STEP_SIZE,
    _build_result_payload,
    fetch_all_layouts,
    query_parser_status,
)
from ingest_chroma import load_json_and_ingest_chroma
from submit_doc_parser_job_advance import (
    ENHANCEMENT_MODE,
    LLM_ENHANCEMENT,
    _parse_output_format,
)

logger = logging.getLogger(__name__)

PROJECT_ROOT = SCRIPT_DIR.parent
DOC_DIR = PROJECT_ROOT / "doc" / "semiconductor_doc"
OUTPUT_DIR = PROJECT_ROOT / "doc_result" / "semiconductor_res"
DEFAULT_COLLECTION = "semiconductor"


def json_path_for_pdf(pdf_path: Path) -> Path:
    return OUTPUT_DIR / f"{pdf_path.stem}.json"


def should_skip_parse(json_path: Path) -> bool:
    """同名 JSON 已存在则跳过文档解析 API，节约资源。"""
    return json_path.is_file()


def is_json_complete(json_path: Path) -> bool:
    if not json_path.is_file():
        return False
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            payload = json.load(f)
    except (OSError, json.JSONDecodeError):
        return False
    return payload.get("Completed") is True


def submit_pdf_job(file_path: Path) -> str:
    client = create_client()
    file_name = file_path.name
    file_name_extension = file_path.suffix.lstrip(".") or "pdf"

    request_kwargs = {
        "file_name": file_name,
        "file_name_extension": file_name_extension,
        "output_format": _parse_output_format(),
        "llm_enhancement": LLM_ENHANCEMENT,
    }
    if LLM_ENHANCEMENT and ENHANCEMENT_MODE:
        request_kwargs["enhancement_mode"] = ENHANCEMENT_MODE

    with open(file_path, "rb") as pdf_file:
        request = docmind_api20220711_models.SubmitDocParserJobAdvanceRequest(
            file_url_object=pdf_file,
            **request_kwargs,
        )
        runtime = util_models.RuntimeOptions()
        try:
            response = client.submit_doc_parser_job_advance(request, runtime)
            response_body = response.body.to_map()
            return response_body["Data"]["Id"]
        except Exception as error:
            UtilClient.assert_as_string(error.message)
            raise


def save_parser_result(
    pdf_name: str,
    task_id: str,
    output_dir: Path,
    *,
    layout_step_size: int = DEFAULT_LAYOUT_STEP_SIZE,
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / f"{Path(pdf_name).stem}.json"

    status_data = query_parser_status(task_id)
    status = str(status_data.get("Status") or "").lower()
    logger.info(
        "status=%s processing=%s",
        status_data.get("Status"),
        status_data.get("Processing"),
    )

    if status == "success":
        layouts = fetch_all_layouts(task_id, layout_step_size=layout_step_size)
        payload = _build_result_payload(
            completed=True,
            status_data=status_data,
            pdf_name=pdf_name,
            layouts=layouts,
        )
    else:
        payload = _build_result_payload(
            completed=False,
            status_data=status_data,
            pdf_name=pdf_name,
        )

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=4)
    logger.info("Wrote parser result to %s", output_file)
    return output_file


def wait_for_result(
    pdf_name: str,
    task_id: str,
    output_dir: Path,
    *,
    interval_seconds: int = 5,
    max_attempts: int = 60,
    layout_step_size: int = DEFAULT_LAYOUT_STEP_SIZE,
) -> Path:
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
            return save_parser_result(
                pdf_name,
                task_id,
                output_dir,
                layout_step_size=layout_step_size,
            )

        if status == "fail":
            raise RuntimeError(f"DocParser job failed: {task_id} status={status_data}")

        if attempt < max_attempts:
            time.sleep(interval_seconds)

    raise TimeoutError(
        f"DocParser result is still not completed after {max_attempts} attempts: {task_id}"
    )


def process_pdf(
    pdf_path: Path,
    *,
    collection_name: str,
    force: bool,
    ingest_only: bool,
    parse_only: bool,
    interval_seconds: int,
    max_attempts: int,
    layout_step_size: int,
) -> None:
    json_path = json_path_for_pdf(pdf_path)
    logger.info("Processing %s", pdf_path.name)

    if ingest_only:
        if not json_path.is_file():
            raise FileNotFoundError(f"ingest-only 模式需要已有 JSON: {json_path}")
        if not is_json_complete(json_path):
            raise RuntimeError(f"JSON 未完成解析，无法入库: {json_path}")
        logger.info("ingest-only: using existing result %s", json_path)
    elif force or not should_skip_parse(json_path):
        logger.info("Submitting parse job for %s", pdf_path)
        task_id = submit_pdf_job(pdf_path)
        logger.info("Submitted task_id=%s", task_id)
        time.sleep(interval_seconds)
        json_path = wait_for_result(
            pdf_path.name,
            task_id,
            OUTPUT_DIR,
            interval_seconds=interval_seconds,
            max_attempts=max_attempts,
            layout_step_size=layout_step_size,
        )
        logger.info("Parser result saved to %s", json_path)
    else:
        logger.info("Skipping parse, JSON already exists: %s", json_path)

    if parse_only:
        logger.info("parse-only mode, skipping ingest")
        return

    if not is_json_complete(json_path):
        raise RuntimeError(f"解析未完成，无法入库: {json_path}")

    logger.info("Ingesting into collection=%s", collection_name)
    total = load_json_and_ingest_chroma(json_path, collection_name=collection_name)
    logger.info("Ingested %d vectors", total)


def main() -> None:
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from rag.logging_config import configure_logging

    configure_logging()
    parser = argparse.ArgumentParser(
        description="批量解析 doc/semiconductor_doc PDF（大模型版）并入库 Chroma"
    )
    parser.add_argument(
        "--collection-name",
        default=os.environ.get("CHROMA_COLLECTION_NAME_SEMICONDUCTOR", DEFAULT_COLLECTION),
        help=f"Chroma 集合名称（默认: {DEFAULT_COLLECTION}）",
    )
    parser.add_argument("--interval-seconds", type=int, default=5)
    parser.add_argument("--max-attempts", type=int, default=60)
    parser.add_argument(
        "--layout-step-size",
        type=int,
        default=int(os.environ.get("DOCMIND_LAYOUT_STEP_SIZE", str(DEFAULT_LAYOUT_STEP_SIZE))),
    )
    parser.add_argument("--parse-only", action="store_true", help="只解析，不入库")
    parser.add_argument("--ingest-only", action="store_true", help="只入库已有 JSON，跳过解析")
    parser.add_argument("--force", action="store_true", help="忽略已有同名 JSON，强制重新解析")
    args = parser.parse_args()

    if args.parse_only and args.ingest_only:
        parser.error("--parse-only 与 --ingest-only 不能同时使用")

    if not DOC_DIR.is_dir():
        raise FileNotFoundError(f"未找到 PDF 目录: {DOC_DIR}")

    pdf_files = sorted(DOC_DIR.glob("*.pdf"))
    if not pdf_files:
        raise FileNotFoundError(f"目录下没有 PDF 文件: {DOC_DIR}")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    logger.info("PDF dir: %s", DOC_DIR)
    logger.info("JSON output: %s", OUTPUT_DIR)
    logger.info("PDF files to process: %d", len(pdf_files))

    for pdf_path in pdf_files:
        process_pdf(
            pdf_path,
            collection_name=args.collection_name,
            force=args.force,
            ingest_only=args.ingest_only,
            parse_only=args.parse_only,
            interval_seconds=args.interval_seconds,
            max_attempts=args.max_attempts,
            layout_step_size=args.layout_step_size,
        )

    logger.info("Batch processing complete")


if __name__ == "__main__":
    main()
