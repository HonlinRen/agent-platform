# -*- coding: utf-8 -*-
"""通过 ModelScope（国内）将 Rerank 模型下载到项目 models/ 目录。"""
from __future__ import annotations

import logging
import os
import shutil
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
MODELSCOPE_REPO = os.environ.get("RERANK_MODELSCOPE_REPO", "Xorbits/bge-reranker-base")
LOCAL_DIR = Path(os.environ.get("RERANK_MODEL_PATH", PROJECT_ROOT / "models" / "bge-reranker-base"))

logger = logging.getLogger(__name__)


def main() -> None:
    import sys

    sys.path.insert(0, str(PROJECT_ROOT))
    from rag.logging_config import configure_logging

    configure_logging()
    from modelscope import snapshot_download

    LOCAL_DIR.parent.mkdir(parents=True, exist_ok=True)
    logger.info("Downloading %s from ModelScope", MODELSCOPE_REPO)
    logger.info("Target directory: %s", LOCAL_DIR)

    cache_dir = PROJECT_ROOT / "models" / "_modelscope_cache"
    downloaded = Path(
        snapshot_download(
            MODELSCOPE_REPO,
            cache_dir=str(cache_dir),
        )
    )

    if LOCAL_DIR.exists():
        shutil.rmtree(LOCAL_DIR)
    shutil.copytree(downloaded, LOCAL_DIR)

    logger.info("Download complete. Local model path: %s", LOCAL_DIR)
    logger.info("If needed: pip install sentencepiece")


if __name__ == "__main__":
    main()
