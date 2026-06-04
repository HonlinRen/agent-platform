# -*- coding: utf-8 -*-
import argparse
import hashlib
import json
import logging
import os
import uuid
from collections import defaultdict
from pathlib import Path
from typing import Any, List

import chromadb
from langchain_community.embeddings import DashScopeEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
JSON_INPUT_FILE = PROJECT_ROOT / "doc_result" / "security-whitepaper_8.json"

DASHSCOPE_API_KEY = os.environ.get("DASHSCOPE_API_KEY") or os.environ.get("API_KEY")
EMBEDDING_MODEL = os.environ.get("DASHSCOPE_EMBEDDING_MODEL", "text-embedding-v3")
CHUNK_SIZE = int(os.environ.get("CHUNK_SIZE", "800"))
CHUNK_OVERLAP = int(os.environ.get("CHUNK_OVERLAP", "150"))
CHROMA_HOST = os.environ.get("CHROMA_HOST", "127.0.0.1")
CHROMA_PORT = int(os.environ.get("CHROMA_PORT", "8000"))
CHROMA_COLLECTION_NAME = os.environ.get("CHROMA_COLLECTION_NAME", "white_paper_iot")


def to_int(value, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _should_skip_layout(layout: dict) -> bool:
    layout_type = str(layout.get("type") or "").lower()
    sub_type = str(layout.get("subType") or "").lower()
    return layout_type in {"foot", "foot_image", "figure"} or "footer" in sub_type


def extract_layout_text(layout: dict) -> str:
    text = (layout.get("text") or "").strip()
    if not text or text == "[empty]":
        return ""
    if _should_skip_layout(layout):
        return ""
    return text


def extract_parser_layout_text(layout: dict) -> str:
    if _should_skip_layout(layout):
        return ""

    parts: list[str] = []
    markdown = (layout.get("markdownContent") or "").strip()
    if markdown:
        parts.append(markdown)

    llm_result = (layout.get("llmResult") or "").strip()
    if llm_result:
        parts.append(llm_result)

    if not parts:
        text = (layout.get("text") or "").strip()
        if text and text != "[empty]":
            parts.append(text)

    return "\n\n".join(parts).strip()


def _coerce_page_nums(page_num_value) -> list:
    if page_num_value is None:
        return []
    if isinstance(page_num_value, (list, tuple)):
        return list(page_num_value)
    return [page_num_value]


def _layout_page_number(layout: dict) -> int:
    page_nums = _coerce_page_nums(layout.get("pageNum"))
    if not page_nums:
        return 1
    return min(to_int(page_num) + 1 for page_num in page_nums)


def normalize_legacy_pages(parsed_pages: List[dict], source_name: str) -> List[dict]:
    normalized = []
    for page in parsed_pages:
        final_chunk = (
            page.get("final_chunk")
            or page.get("raw_text")
            or page.get("text")
            or ""
        ).strip()
        if not final_chunk:
            continue

        normalized.append(
            {
                "doc_name": page.get("doc_name") or f"{source_name}.pdf",
                "page_number": to_int(page.get("page_number")),
                "content_type": page.get("content_type") or "pure_text",
                "final_chunk": final_chunk,
            }
        )
    return normalized


def normalize_docmind_result(payload: dict, source_name: str) -> List[dict]:
    doc_info = payload.get("docInfo") or {}
    doc_name = doc_info.get("orignalDocName") or doc_info.get("originalDocName") or f"{source_name}.pdf"
    grouped_pages = defaultdict(list)

    for layout in payload.get("layouts") or []:
        text = extract_layout_text(layout)
        if not text:
            continue

        page_nums = _coerce_page_nums(layout.get("pageNum"))
        page_number = min((to_int(page_num) + 1 for page_num in page_nums), default=1)
        grouped_pages[page_number].append(text)

    normalized = []
    for page_number in sorted(grouped_pages):
        final_chunk = "\n".join(part.strip() for part in grouped_pages[page_number] if part.strip()).strip()
        if not final_chunk:
            continue

        normalized.append(
            {
                "doc_name": doc_name,
                "page_number": page_number,
                "content_type": "docmind_layout",
                "final_chunk": final_chunk,
            }
        )

    return normalized


def is_doc_parser_payload(data: dict) -> bool:
    if data.get("parser") == "doc_parser":
        return True
    layouts = data.get("layouts") or []
    return any(
        isinstance(layout, dict) and layout.get("markdownContent")
        for layout in layouts
    )


def build_parser_segments(payload: dict, source_name: str) -> tuple[str, list[dict]]:
    doc_info = payload.get("docInfo") or {}
    doc_name = (
        doc_info.get("orignalDocName")
        or doc_info.get("originalDocName")
        or f"{source_name}.pdf"
    )
    segments: list[dict] = []
    for layout in payload.get("layouts") or []:
        text = extract_parser_layout_text(layout)
        if not text:
            continue
        segments.append(
            {
                "text": text,
                "page_number": _layout_page_number(layout),
            }
        )
    return doc_name, segments


def load_json_records(json_path: Path) -> dict[str, Any]:
    with open(json_path, "r", encoding="utf-8") as f:
        payload = json.load(f)

    if isinstance(payload, list):
        return {
            "mode": "pages",
            "pages": normalize_legacy_pages(payload, json_path.stem),
        }

    if isinstance(payload, dict):
        data = payload.get("Data") if isinstance(payload.get("Data"), dict) else payload
        if isinstance(data, dict) and "layouts" in data:
            if is_doc_parser_payload(data):
                doc_name, segments = build_parser_segments(data, json_path.stem)
                return {
                    "mode": "parser",
                    "doc_name": doc_name,
                    "segments": segments,
                }
            return {
                "mode": "pages",
                "pages": normalize_docmind_result(data, json_path.stem),
            }

    raise RuntimeError(f"不支持的 JSON 结构: {json_path}")


def _page_for_offset(offset: int, boundaries: list[tuple[int, int]]) -> int:
    page = boundaries[0][1] if boundaries else 1
    for start, page_number in boundaries:
        if start <= offset:
            page = page_number
        else:
            break
    return page


def build_embeddings() -> DashScopeEmbeddings:
    if not DASHSCOPE_API_KEY:
        raise RuntimeError("Missing environment variable: DASHSCOPE_API_KEY or API_KEY")

    os.environ["DASHSCOPE_API_KEY"] = DASHSCOPE_API_KEY
    return DashScopeEmbeddings(model=EMBEDDING_MODEL)


def compute_doc_version(json_input_file: Path) -> str:
    digest = hashlib.sha256(json_input_file.read_bytes()).hexdigest()
    return digest[:12]


def make_chunk_id(source: str, page_number: int, chunk_index: int) -> str:
    source_id = f"{source}:p{page_number}:c{chunk_index}"
    return str(uuid.uuid5(uuid.NAMESPACE_URL, source_id))


def delete_stale_chunks(collection, source: str, active_ids: set[str]) -> int:
    existing = collection.get(
        where={"source": {"$eq": source}},
        include=[],
    )
    stale_ids = [chunk_id for chunk_id in (existing.get("ids") or []) if chunk_id not in active_ids]
    if not stale_ids:
        return 0

    batch_size = 100
    for start in range(0, len(stale_ids), batch_size):
        collection.delete(ids=stale_ids[start : start + batch_size])
    return len(stale_ids)


def build_chunks(json_input_file: Path, doc_version: str):
    if not json_input_file.exists():
        raise FileNotFoundError(f"未找到数据源 JSON 文件: {json_input_file}")

    logger.info("Reading structured data: %s", json_input_file.name)
    parsed = load_json_records(json_input_file)

    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        separators=["\n\n", "\n", "。", "；", "！", "？", " ", ""],
    )

    source = json_input_file.stem
    texts = []
    metadatas = []
    ids = []

    logger.info("doc_version=%s (source=%s)", doc_version, source)

    if parsed["mode"] == "parser":
        segments = parsed["segments"]
        doc_name = parsed["doc_name"]
        logger.info("Loaded %d DocParser layout blocks", len(segments))
        logger.info("Splitting markdown by layout order")

        boundaries: list[tuple[int, int]] = []
        parts: list[str] = []
        cursor = 0
        for segment in segments:
            boundaries.append((cursor, to_int(segment.get("page_number"), default=1)))
            parts.append(segment["text"])
            cursor += len(segment["text"]) + 2

        full_text = "\n\n".join(parts)
        split_chunks = text_splitter.split_text(full_text)
        search_from = 0
        for chunk_index, chunk in enumerate(split_chunks):
            text = chunk.strip()
            if not text:
                continue

            start = full_text.find(text, search_from)
            if start < 0:
                start = search_from
            page_number = _page_for_offset(start, boundaries)
            search_from = max(search_from, start + len(text))

            texts.append(text)
            metadatas.append(
                {
                    "source": source,
                    "doc_version": doc_version,
                    "document_name": doc_name,
                    "page": page_number,
                    "content_type": "doc_parser_layout",
                    "text": text,
                }
            )
            ids.append(make_chunk_id(source, page_number, chunk_index))
    else:
        parsed_pages = parsed["pages"]
        logger.info("Loaded %d parsed PDF pages", len(parsed_pages))
        logger.info("Splitting page content and injecting metadata")
        for page in parsed_pages:
            page_content = page.get("final_chunk", "")
            if not page_content.strip():
                continue

            page_number = to_int(page.get("page_number"))
            page_chunks = text_splitter.split_text(page_content)
            for chunk_index, chunk in enumerate(page_chunks):
                text = chunk.strip()
                if not text:
                    continue

                texts.append(text)
                metadatas.append(
                    {
                        "source": source,
                        "doc_version": doc_version,
                        "document_name": page.get("doc_name", "unknown"),
                        "page": page_number,
                        "content_type": page.get("content_type", "pure_text"),
                        "text": text,
                    }
                )
                ids.append(make_chunk_id(source, page_number, chunk_index))

    logger.info("Built %d text chunks", len(texts))
    return texts, metadatas, ids, source


def load_json_and_ingest_chroma(
    json_input_file: Path,
    *,
    collection_name: str | None = None,
    doc_version: str | None = None,
    cleanup_stale: bool = True,
    run_test_query: bool = False,
) -> int:
    resolved_version = doc_version or compute_doc_version(json_input_file)
    texts, metadatas, ids, source = build_chunks(json_input_file, resolved_version)
    if not texts:
        logger.warning("No ingestible text generated")
        return 0

    target_collection = collection_name or CHROMA_COLLECTION_NAME

    logger.info("Initializing DashScope embedding engine (%s)", EMBEDDING_MODEL)
    embeddings = build_embeddings()

    logger.info("Connecting to Chroma at %s:%s", CHROMA_HOST, CHROMA_PORT)
    chroma_client = chromadb.HttpClient(host=CHROMA_HOST, port=CHROMA_PORT)
    collection = chroma_client.get_or_create_collection(name=target_collection)

    batch_size = 32
    total = len(texts)
    for start in range(0, total, batch_size):
        batch_texts = texts[start : start + batch_size]
        batch_metadatas = metadatas[start : start + batch_size]
        batch_ids = ids[start : start + batch_size]
        batch_embeddings = embeddings.embed_documents(batch_texts)

        collection.upsert(
            ids=batch_ids,
            documents=batch_texts,
            metadatas=batch_metadatas,
            embeddings=batch_embeddings,
        )
        logger.info("Upserted %d/%d vectors to Chroma", min(start + batch_size, total), total)

    if cleanup_stale:
        removed = delete_stale_chunks(collection, source, set(ids))
        if removed:
            logger.info(
                "Removed %d stale vectors (source=%s, doc_version=%s)",
                removed,
                source,
                resolved_version,
            )
        else:
            logger.info(
                "No stale vectors to remove (source=%s, doc_version=%s)",
                source,
                resolved_version,
            )

    logger.info("Ingest complete: %d vectors in collection %s", total, target_collection)

    if run_test_query:
        query_text = "物联网汽车安全有哪些风险？"
        query_embedding = embeddings.embed_query(query_text)
        results = collection.query(query_embeddings=[query_embedding], n_results=3)

        logger.info("Test query results for: %s", query_text)
        for i, doc_id in enumerate(results["ids"][0]):
            logger.info(
                "Rank %d: id=%s distance=%s metadata=%s text=%s",
                i + 1,
                doc_id,
                results["distances"][0][i],
                results["metadatas"][0][i],
                results["documents"][0][i],
            )

    return total


def main() -> None:
    import sys

    sys.path.insert(0, str(PROJECT_ROOT))
    from rag.logging_config import configure_logging

    configure_logging()
    parser = argparse.ArgumentParser(description="将 DocMind JSON 解析结果写入 Chroma")
    parser.add_argument(
        "--json-path",
        type=Path,
        default=JSON_INPUT_FILE,
        help=f"DocMind 结果 JSON 路径（默认: {JSON_INPUT_FILE.name}）",
    )
    parser.add_argument(
        "--collection-name",
        default=None,
        help=f"Chroma 集合名称（默认: 环境变量 CHROMA_COLLECTION_NAME 或 {CHROMA_COLLECTION_NAME}）",
    )
    parser.add_argument(
        "--test-query",
        action="store_true",
        help="入库完成后执行一次示例检索",
    )
    parser.add_argument(
        "--doc-version",
        default=None,
        help="文档版本号（默认: JSON 文件 sha256 前 12 位）",
    )
    parser.add_argument(
        "--no-cleanup",
        action="store_true",
        help="跳过清理该文档在库中的过时向量（旧版本 / 已删除页）",
    )
    args = parser.parse_args()
    load_json_and_ingest_chroma(
        args.json_path,
        collection_name=args.collection_name,
        doc_version=args.doc_version,
        cleanup_stale=not args.no_cleanup,
        run_test_query=args.test_query,
    )


if __name__ == "__main__":
    main()
