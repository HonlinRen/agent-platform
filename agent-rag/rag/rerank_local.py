from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from typing import Any

# 国内网络默认走镜像；可在 .env 中覆盖 HF_ENDPOINT
os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
LOCAL_MODEL_CANDIDATES = (
    PROJECT_ROOT / "models" / "bge-reranker-base",
    PROJECT_ROOT / "models" / "Xorbits" / "bge-reranker-base",
)

RERANK_ENABLED = os.environ.get("RERANK_ENABLED", "true").lower() in {"1", "true", "yes"}
RERANK_MODEL = os.environ.get("RERANK_MODEL", "BAAI/bge-reranker-base")
RERANK_MODEL_PATH = os.environ.get("RERANK_MODEL_PATH", "").strip()
RERANK_DEVICE = os.environ.get("RERANK_DEVICE", "auto")

_model = None
_model_error: str | None = None


def is_valid_local_model(path: Path) -> bool:
    config_file = path / "config.json"
    model_file = path / "model.safetensors"
    if not config_file.exists() or not model_file.exists():
        return False

    try:
        import json

        with open(config_file, encoding="utf-8") as f:
            config = json.load(f)
        return bool(config.get("model_type") or config.get("architectures"))
    except (OSError, json.JSONDecodeError):
        return False


def resolve_model_source() -> tuple[str, bool]:
    if RERANK_MODEL_PATH:
        path = Path(RERANK_MODEL_PATH)
        if not is_valid_local_model(path):
            raise FileNotFoundError(f"RERANK_MODEL_PATH 不是有效的本地模型目录: {path}")
        return str(path), True

    for candidate in LOCAL_MODEL_CANDIDATES:
        if is_valid_local_model(candidate):
            return str(candidate), True

    return RERANK_MODEL, False


def resolve_device() -> str:
    import torch

    if RERANK_DEVICE not in {"", "auto"}:
        if RERANK_DEVICE == "cuda" and not torch.cuda.is_available():
            raise RuntimeError(
                "RERANK_DEVICE=cuda 但当前 PyTorch 检测不到 GPU。"
                "请安装 CUDA 版 PyTorch: "
                "pip install torch --index-url https://download.pytorch.org/whl/cu124"
            )
        return RERANK_DEVICE

    if torch.cuda.is_available():
        gpu_name = torch.cuda.get_device_name(0)
        logger.info("Rerank using GPU: %s", gpu_name)
        return "cuda"

    logger.warning("CUDA unavailable, Rerank will use CPU (torch=%s)", torch.__version__)
    if "+cpu" in torch.__version__ and sys.version_info >= (3, 13):
        logger.warning(
            "Python 3.13 on Windows typically has CPU-only PyTorch. "
            "For GPU, use Python 3.12 and: pip install torch --index-url https://download.pytorch.org/whl/cu124"
        )
    elif "+cpu" in torch.__version__:
        logger.warning(
            "Install CUDA PyTorch: pip install torch --index-url https://download.pytorch.org/whl/cu124"
        )
    return "cpu"


def _load_model():
    global _model, _model_error

    if _model is not None:
        return _model
    if _model_error is not None:
        return None

    if not RERANK_ENABLED:
        return None

    try:
        from sentence_transformers import CrossEncoder

        model_source, local_only = resolve_model_source()
        device = resolve_device()
        logger.info(
            "Loading rerank model: %s (device=%s, local_only=%s)",
            model_source,
            device,
            local_only,
        )

        load_kwargs: dict[str, Any] = {}
        if local_only:
            load_kwargs["local_files_only"] = True

        _model = CrossEncoder(model_source, device=device, **load_kwargs)
        return _model
    except Exception as exc:
        _model_error = str(exc)
        logger.warning("Rerank model load failed, falling back to vector order: %s", exc)
        logger.warning(
            "Download model locally (ModelScope recommended): "
            "pip install modelscope sentencepiece && python scripts/download_rerank_model.py"
        )
        return None


def preload_rerank_model() -> bool:
    return _load_model() is not None


def _snippet(text: str, max_len: int = 50) -> str:
    one_line = " ".join(str(text).split())
    return one_line if len(one_line) <= max_len else one_line[:max_len] + "..."


def rerank_candidates(
    query: str,
    candidates: list[dict[str, Any]],
    top_k: int,
) -> list[dict[str, Any]]:
    from rag.metrics import record_rerank

    if not candidates:
        return []

    record_rerank()

    if not RERANK_ENABLED or len(candidates) <= top_k:
        logger.info("Rerank skipped or candidates<=%d, using top %d by vector order", top_k, top_k)
        return candidates[:top_k]

    model = _load_model()
    if model is None:
        logger.warning("Rerank model unavailable, keeping top %d by vector order", top_k)
        return candidates[:top_k]

    pairs = [(query, str(item.get("text", ""))) for item in candidates]
    scores = model.predict(pairs)

    ranked = sorted(
        zip(candidates, scores),
        key=lambda item: float(item[1]),
        reverse=True,
    )
    selected: list[dict[str, Any]] = []
    logger.info("Rerank %d candidates -> Top-%d", len(candidates), top_k)
    for rank, (item, score) in enumerate(ranked[:top_k], start=1):
        enriched = dict(item)
        enriched["rerank_score"] = float(score)
        selected.append(enriched)
        meta = enriched.get("metadata") or {}
        source = meta.get("source", "unknown")
        page = meta.get("page", meta.get("page_number", "?"))
        logger.info(
            "  [%d] rerank_score=%.4f | %s 第%s页 | %s",
            rank,
            float(score),
            source,
            page,
            _snippet(enriched.get("text", "")),
        )
    return selected
