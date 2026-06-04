# -*- coding: utf-8 -*-
import json
import logging
import os
from pathlib import Path
from typing import Any

from alibabacloud_docmind_api20220711 import models as docmind_api20220711_models
from alibabacloud_tea_util.client import Client as UtilClient

from docmind_client import create_client

logger = logging.getLogger(__name__)

DEFAULT_LAYOUT_STEP_SIZE = int(os.environ.get("DOCMIND_LAYOUT_STEP_SIZE", "100"))


def _to_map(value: Any) -> dict:
    if value is None:
        return {}
    if hasattr(value, "to_map"):
        return value.to_map()
    if isinstance(value, dict):
        return value
    return {}


def query_parser_status(task_id: str) -> dict:
    client = create_client()
    request = docmind_api20220711_models.QueryDocParserStatusRequest(id=task_id)
    try:
        response = client.query_doc_parser_status(request)
        return _to_map(response.body.data)
    except Exception as error:
        UtilClient.assert_as_string(error.message)
        raise


def fetch_all_layouts(task_id: str, layout_step_size: int = DEFAULT_LAYOUT_STEP_SIZE) -> list[dict]:
    client = create_client()
    all_layouts: list[dict] = []
    layout_num = 0

    while True:
        request = docmind_api20220711_models.GetDocParserResultRequest(
            id=task_id,
            layout_num=layout_num,
            layout_step_size=layout_step_size,
        )
        try:
            response = client.get_doc_parser_result(request)
        except Exception as error:
            UtilClient.assert_as_string(error.message)
            raise

        result_data = _to_map(response.body.data)
        layouts = result_data.get("layouts") or []
        if not layouts:
            break

        all_layouts.extend(layouts)
        layout_num += len(layouts)
        if len(layouts) < layout_step_size:
            break

    return all_layouts


def _build_result_payload(
    *,
    completed: bool,
    status_data: dict,
    pdf_name: str,
    layouts: list[dict] | None = None,
) -> dict:
    payload: dict[str, Any] = {
        "Completed": completed,
        "Status": status_data.get("Status"),
        "Processing": status_data.get("Processing"),
        "NumberOfSuccessfulParsing": status_data.get("NumberOfSuccessfulParsing"),
    }
    if layouts is not None:
        payload["Data"] = {
            "docInfo": {"originalDocName": pdf_name},
            "layouts": layouts,
            "parser": "doc_parser",
            "status": status_data,
        }
    return payload


def get_doc_result(
    pdf_name: str,
    task_id: str,
    *,
    layout_step_size: int = DEFAULT_LAYOUT_STEP_SIZE,
) -> Path:
    output_dir = Path(__file__).resolve().parent.parent / "doc_result"
    output_dir.mkdir(exist_ok=True)
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
    elif status == "fail":
        payload = _build_result_payload(
            completed=False,
            status_data=status_data,
            pdf_name=pdf_name,
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


if __name__ == "__main__":
    get_doc_result("white-paper-IOT_43.pdf", "docmind-20260520-f0ddcee63d0e4fad83b884a9bdea7fd5")
