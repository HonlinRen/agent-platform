# -*- coding: utf-8 -*-
import logging
import os
from pathlib import Path

from alibabacloud_docmind_api20220711 import models as docmind_api20220711_models
from alibabacloud_tea_util import models as util_models
from alibabacloud_tea_util.client import Client as UtilClient

from docmind_client import create_client

logger = logging.getLogger(__name__)

DOC_DIR = Path(__file__).resolve().parent.parent / "doc"
OUTPUT_FORMAT = os.environ.get("DOCMIND_OUTPUT_FORMAT", "markdown")
LLM_ENHANCEMENT = os.environ.get("DOCMIND_LLM_ENHANCEMENT", "false").lower() in {
    "1",
    "true",
    "yes",
}
ENHANCEMENT_MODE = os.environ.get("DOCMIND_ENHANCEMENT_MODE") or None


def _parse_output_format() -> list[str]:
    return [part.strip() for part in OUTPUT_FORMAT.split(",") if part.strip()]


def submit_doc_parser_job(file_name: str, file_name_extension: str) -> str:
    client = create_client()
    file_path = DOC_DIR / file_name

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


if __name__ == "__main__":
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from rag.logging_config import configure_logging

    configure_logging()
    task_id = submit_doc_parser_job("white-paper-IOT_43.pdf", "pdf")
    logger.info("Submitted task_id=%s", task_id)
