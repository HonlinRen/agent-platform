from __future__ import annotations

import logging
import os
import time
from collections.abc import Iterator
from typing import Any
os.environ.setdefault("NO_PROXY", "localhost,127.0.0.1,::1")
os.environ.setdefault("no_proxy", "localhost,127.0.0.1,::1")
os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")

import chromadb
from langchain_community.chat_message_histories import ChatMessageHistory
from langchain_community.embeddings import DashScopeEmbeddings
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.prompts import PromptTemplate
from langchain_openai import ChatOpenAI

from rag.knowledge_bases import DEFAULT_COLLECTION, get_domain_hint, validate_collection_name
from rag.memory.formatting import format_memory_placeholder
from rag.llm_timing import timed_embedding, timed_llm_invoke
from rag.metrics import record_and_track_llm, record_embedding, record_retrieval_score
from rag.request_timing import get_request_timing
from rag.reject import should_reject
from rag.rerank_local import RERANK_ENABLED, preload_rerank_model, rerank_candidates
from rag.telemetry import (
    RAG_CHROMA_QUERY_DURATION,
    RAG_RERANK_DURATION,
    RAG_RETRIEVAL_CANDIDATES,
    get_tenant_id,
    log_extra,
    span,
)

logger = logging.getLogger(__name__)
VERBOSE_RETRIEVAL = os.environ.get("RAG_VERBOSE_RETRIEVAL", "false").lower() in {"1", "true", "yes"}
DASHSCOPE_API_KEY = os.environ.get("DASHSCOPE_API_KEY") or os.environ.get("API_KEY")
EMBEDDING_MODEL = os.environ.get("DASHSCOPE_EMBEDDING_MODEL", "text-embedding-v3")
LLM_MODEL = os.environ.get("DASHSCOPE_LLM_MODEL", "qwen-plus")
DASHSCOPE_BASE_URL = os.environ.get(
    "DASHSCOPE_BASE_URL",
    "https://dashscope.aliyuncs.com/compatible-mode/v1",
)
WINDOW_SIZE = int(os.environ.get("CHAT_WINDOW_SIZE", "5"))
CHROMA_HOST = os.environ.get("CHROMA_HOST", "127.0.0.1")
CHROMA_PORT = int(os.environ.get("CHROMA_PORT", "8000"))
CHROMA_COLLECTION_NAME = DEFAULT_COLLECTION
RETRIEVAL_TOP_N = int(os.environ.get("RETRIEVAL_TOP_N", "15"))
RETRIEVAL_FINAL_TOP_K = int(os.environ.get("RETRIEVAL_FINAL_TOP_K", "5"))
MAX_TOOL_ROUNDS = int(os.environ.get("MAX_TOOL_ROUNDS", "3"))
MAX_RETRIEVE_RETRIES = int(os.environ.get("MAX_RETRIEVE_RETRIES", "2"))


def build_system_prompt(domain_hint: str) -> str:
    return f"""你是一个{domain_hint}助手。
回答要专业、简洁、准确。

要求：
1. 必须优先依据 LOCAL DOCUMENT 中提供的本地知识库内容回答。
2. 如果使用了 LOCAL DOCUMENT 中的信息，必须在相关句子后标注来源，格式为：[来源：文件名 第N页]。
3. 如果 LOCAL DOCUMENT 中没有足够依据，请明确说明“本地知识库上下文中未找到充分依据”，不要编造。
4. 不要引用 CHAT HISTORY、会话摘要或租户背景作为事实来源，这些只用于理解上下文。"""


def build_direct_system_prompt(domain_hint: str) -> str:
    return f"""你是一个友好的{domain_hint}助手。
用户当前问题是纯闲聊或寒暄（如问候、感谢、自我介绍等），与知识库查询和联网搜索无关。
请简洁、自然地回应，不要编造知识库具体内容或行业事实。"""


def build_web_system_prompt(domain_hint: str) -> str:
    return f"""你是一个{domain_hint}助手。
当前回答必须基于 WEB DOCUMENT 中的互联网公开检索结果，这些内容**不是**本地知识库文档。

要求：
1. 回答开头或首段必须明确声明：以下信息来自互联网公开检索，非本地知识库内容。
2. 引用 WEB DOCUMENT 中的信息时，使用格式：[来源：标题 URL]。
3. 不得将互联网信息伪装成本地知识库文档依据。
4. 不要引用 CHAT HISTORY、会话摘要或租户背景作为事实来源，这些只用于理解上下文。"""


def build_hybrid_system_prompt(domain_hint: str) -> str:
    return f"""你是一个{domain_hint}助手。
当前同时提供了本地知识库检索结果（LOCAL DOCUMENT）和互联网公开检索结果（WEB DOCUMENT）。

要求：
1. 优先依据 LOCAL DOCUMENT 回答；若 LOCAL DOCUMENT 信息不足，可补充 WEB DOCUMENT 中的内容。
2. 引用 LOCAL DOCUMENT 时使用格式：[来源：文件名 第N页]。
3. 引用 WEB DOCUMENT 时使用格式：[来源：标题 URL]，并明确该部分来自互联网公开检索。
4. 不得将互联网信息伪装成本地知识库依据。
5. 不要引用 CHAT HISTORY、会话摘要或租户背景作为事实来源，这些只用于理解上下文。"""


def _snippet(text: str, max_len: int = 50) -> str:
    one_line = " ".join(str(text).split())
    return one_line if len(one_line) <= max_len else one_line[: max_len - 3] + "..."


def chunk_to_text(chunk: Any) -> str:
    if chunk is None:
        return ""
    if isinstance(chunk, str):
        return chunk
    content = getattr(chunk, "content", None)
    if isinstance(content, str):
        return content
    return str(chunk)


def llm_output_to_text(output: Any) -> str:
    if isinstance(output, str):
        return output.strip()
    content = getattr(output, "content", None)
    if isinstance(content, str):
        return content.strip()
    return str(output).strip()


def _build_chat_llm(*, api_key: str, streaming: bool, temperature: float) -> ChatOpenAI:
    return ChatOpenAI(
        model=LLM_MODEL,
        api_key=api_key,
        base_url=DASHSCOPE_BASE_URL,
        temperature=temperature,
        streaming=streaming,
    )


def _memory_context_block() -> str:
    return (
        "【租户背景】\n{tenant_profile_summary}\n\n"
        "【会话摘要】\n{conversation_summary}\n\n"
        "【最近对话】\n{recent_messages_text}\n\n"
    )


class CarSafetyWhitepaperAssistant:
    def __init__(self, collection_name: str | None = None) -> None:
        if not DASHSCOPE_API_KEY:
            raise RuntimeError("Missing environment variable: DASHSCOPE_API_KEY or API_KEY")

        self.collection_name = validate_collection_name(collection_name)
        domain_hint = get_domain_hint(self.collection_name)
        self.system_prompt = build_system_prompt(domain_hint)
        self.direct_system_prompt = build_direct_system_prompt(domain_hint)
        self.web_system_prompt = build_web_system_prompt(domain_hint)
        self.hybrid_system_prompt = build_hybrid_system_prompt(domain_hint)

        os.environ["DASHSCOPE_API_KEY"] = DASHSCOPE_API_KEY
        self.embeddings = DashScopeEmbeddings(model=EMBEDDING_MODEL)
        self.client = chromadb.HttpClient(host=CHROMA_HOST, port=CHROMA_PORT)
        self.collection = self.client.get_or_create_collection(name=self.collection_name)
        self.chat_llm = _build_chat_llm(api_key=DASHSCOPE_API_KEY, streaming=True, temperature=0.3)
        self.router_llm = _build_chat_llm(api_key=DASHSCOPE_API_KEY, streaming=False, temperature=0.0)
        self.llm = self.chat_llm
        logger.info(
            "LLM=%s, base_url=%s, RETRIEVAL_TOP_N=%d, RETRIEVAL_FINAL_TOP_K=%d, Chroma collection=%s",
            LLM_MODEL,
            DASHSCOPE_BASE_URL,
            RETRIEVAL_TOP_N,
            RETRIEVAL_FINAL_TOP_K,
            self.collection_name,
        )
        if RERANK_ENABLED:
            preload_rerank_model()
        self.rewrite_prompt = PromptTemplate(
            input_variables=[
                "human_input",
                "tenant_profile_summary",
                "conversation_summary",
                "recent_messages_text",
            ],
            template=(
                "你是一个检索问题改写助手。请根据租户背景、会话摘要和最近对话，"
                "将用户当前问题改写成一个语义完整、适合向量检索的独立问题。\n"
                "要求：\n"
                "1. 只输出改写后的问题，不要回答问题。\n"
                "2. 如果当前问题已经完整，不要扩写无关信息。\n"
                f"3. 保留{domain_hint}相关的关键实体、约束和指代关系。\n\n"
                + _memory_context_block()
                + "当前问题：{human_input}\n"
                "改写后问题："
            ),
        )
        memory_block = _memory_context_block()
        self.prompt = PromptTemplate(
            input_variables=[
                "human_input",
                "context",
                "tenant_profile_summary",
                "conversation_summary",
                "recent_messages_text",
            ],
            template=(
                self.system_prompt
                + "\n\n"
                + memory_block
                + "=====BEGIN LOCAL DOCUMENT=====\n"
                + "{context}\n"
                + "=====END LOCAL DOCUMENT=====\n\n"
                + "=====BEGIN CONVERSATION=====\n"
                + "Human: {human_input}\n"
                + "AI:"
            ),
        )
        self.web_prompt = PromptTemplate(
            input_variables=[
                "human_input",
                "context",
                "tenant_profile_summary",
                "conversation_summary",
                "recent_messages_text",
            ],
            template=(
                self.web_system_prompt
                + "\n\n"
                + memory_block
                + "=====BEGIN WEB DOCUMENT=====\n"
                + "{context}\n"
                + "=====END WEB DOCUMENT=====\n\n"
                + "=====BEGIN CONVERSATION=====\n"
                + "Human: {human_input}\n"
                + "AI:"
            ),
        )
        self.hybrid_prompt = PromptTemplate(
            input_variables=[
                "human_input",
                "local_context",
                "web_context",
                "tenant_profile_summary",
                "conversation_summary",
                "recent_messages_text",
            ],
            template=(
                self.hybrid_system_prompt
                + "\n\n"
                + memory_block
                + "=====BEGIN LOCAL DOCUMENT=====\n"
                + "{local_context}\n"
                + "=====END LOCAL DOCUMENT=====\n\n"
                + "=====BEGIN WEB DOCUMENT=====\n"
                + "{web_context}\n"
                + "=====END WEB DOCUMENT=====\n\n"
                + "=====BEGIN CONVERSATION=====\n"
                + "Human: {human_input}\n"
                + "AI:"
            ),
        )

    def recall_candidates(self, query: str, *, thread_id: str | None = None) -> list[dict[str, Any]]:
        tenant = get_tenant_id() or "default_tenant"
        with span("dashscope.embedding"):
            record_embedding()
            vec = timed_embedding(lambda: self.embeddings.embed_query(query), thread_id=thread_id)

        recall_count = max(RETRIEVAL_TOP_N, RETRIEVAL_FINAL_TOP_K)
        chroma_start = time.perf_counter()
        with span("chroma.query", {"rag.collection": self.collection_name}):
            result = self.collection.query(
                query_embeddings=[vec],
                n_results=recall_count,
                include=["documents", "metadatas", "distances"],
            )
        chroma_ms = int((time.perf_counter() - chroma_start) * 1000)
        RAG_CHROMA_QUERY_DURATION.labels(tenant=tenant, collection=self.collection_name).observe(chroma_ms / 1000.0)
        timing = get_request_timing(thread_id)
        if timing is not None:
            timing.record_chroma(chroma_ms)

        candidates: list[dict[str, Any]] = []
        documents = (result.get("documents") or [[]])[0]
        metadatas = (result.get("metadatas") or [[]])[0]
        distances = (result.get("distances") or [[]])[0]
        for document, metadata, distance in zip(documents, metadatas, distances):
            metadata = metadata or {}
            text = str(document or metadata.get("text", "")).strip()
            if not text:
                continue
            candidates.append({"text": text, "metadata": metadata, "distance": distance})
        RAG_RETRIEVAL_CANDIDATES.labels(tenant=tenant, collection=self.collection_name).observe(len(candidates))
        return candidates

    def retrieve_and_rank(self, query: str, *, thread_id: str | None = None) -> list[dict[str, Any]]:
        tenant = get_tenant_id() or "default_tenant"
        with span("rag.retrieve", {"rag.collection": self.collection_name}):
            candidates = self.recall_candidates(query, thread_id=thread_id)
            self._log_retrieval_candidates(query, candidates)

            rerank_start = time.perf_counter()
            with span("rerank"):
                ranked = rerank_candidates(query, candidates, top_k=RETRIEVAL_FINAL_TOP_K)
            rerank_ms = int((time.perf_counter() - rerank_start) * 1000)
            RAG_RERANK_DURATION.labels(tenant=tenant, collection=self.collection_name).observe(rerank_ms / 1000.0)
            timing = get_request_timing(thread_id)
            if timing is not None:
                timing.record_rerank(rerank_ms)

            if ranked:
                top_score = ranked[0].get("rerank_score")
                if top_score is None:
                    distance = ranked[0].get("distance")
                    if isinstance(distance, (int, float)):
                        top_score = max(0.0, 1.0 - float(distance))
                if isinstance(top_score, (int, float)):
                    record_retrieval_score(float(top_score), tenant=tenant, collection=self.collection_name)

            return ranked

    def _log_retrieval_candidates(self, query: str, candidates: list[dict[str, Any]]) -> None:
        extra = log_extra()
        logger.info(
            "vector recall returned %d candidates for query=%s",
            len(candidates),
            query,
            extra=extra,
        )
        if VERBOSE_RETRIEVAL:
            logger.debug(
                "vector recall: %d candidates, query=%s",
                len(candidates),
                query,
                extra=extra,
            )
            for rank, item in enumerate(candidates[:10], start=1):
                metadata = item.get("metadata") or {}
                source = metadata.get("source", "unknown")
                page = metadata.get("page", metadata.get("page_number", "?"))
                distance = item.get("distance")
                dist_text = f"{distance:.4f}" if isinstance(distance, (int, float)) else "?"
                logger.debug(
                    "  [%d] distance=%s | %s 第%s页 | %s",
                    rank,
                    dist_text,
                    source,
                    page,
                    _snippet(item.get("text", "")),
                    extra=extra,
                )
            logger.debug(
                "rerank will select Top-%d from %d candidates",
                RETRIEVAL_FINAL_TOP_K,
                len(candidates),
                extra=extra,
            )

    @staticmethod
    def format_context(ranked: list[dict[str, Any]]) -> str:
        context_parts: list[str] = []
        for item in ranked:
            metadata = item.get("metadata") or {}
            text = str(item.get("text", "")).strip()
            source = metadata.get("source", "unknown")
            page = metadata.get("page", metadata.get("page_number", "?"))
            context_parts.append(f"来源：{source} 第{page}页\n内容：{text}")
        return "\n".join(context_parts)

    @staticmethod
    def extract_citations(ranked: list[dict[str, Any]]) -> list[dict[str, Any]]:
        citations: list[dict[str, Any]] = []
        seen: set[tuple[str, Any]] = set()
        for item in ranked:
            metadata = item.get("metadata") or {}
            source = str(metadata.get("source", "unknown"))
            page = metadata.get("page", metadata.get("page_number", "?"))
            key = (source, page)
            if key in seen:
                continue
            seen.add(key)
            citations.append({"source": source, "page": page})
        return citations

    def get_context(self, query: str) -> str:
        ranked = self.retrieve_and_rank(query)
        return self.format_context(ranked)

    def get_chunk_by_source(self, source: str, page: int | str) -> list[dict[str, Any]]:
        page_val = int(page) if str(page).isdigit() else page
        where: dict[str, Any] = {"source": source}
        if isinstance(page_val, int):
            where["page"] = page_val
        result = self.collection.get(where=where, include=["documents", "metadatas"])
        documents = result.get("documents") or []
        metadatas = result.get("metadatas") or []
        chunks: list[dict[str, Any]] = []
        for document, metadata in zip(documents, metadatas):
            metadata = metadata or {}
            text = str(document or metadata.get("text", "")).strip()
            if text:
                chunks.append({"text": text, "metadata": metadata})
        return chunks

    def list_collection_stats(self) -> dict[str, Any]:
        count = self.collection.count()
        sample = self.collection.get(limit=min(count, 500), include=["metadatas"])
        sources: set[str] = set()
        for metadata in sample.get("metadatas") or []:
            metadata = metadata or {}
            source = metadata.get("source")
            if source:
                sources.add(str(source))
        return {
            "collection": self.collection_name,
            "document_count": count,
            "sources": sorted(sources),
        }

    def _memory_prompt_fields(
        self,
        *,
        tenant_profile_summary: str = "",
        conversation_summary: str = "",
        recent_messages_text: str = "无历史对话",
    ) -> dict[str, str]:
        return {
            "tenant_profile_summary": format_memory_placeholder(tenant_profile_summary),
            "conversation_summary": format_memory_placeholder(conversation_summary),
            "recent_messages_text": recent_messages_text or "无历史对话",
        }

    def rewrite_query_with_memory(
        self,
        query: str,
        *,
        tenant_profile_summary: str = "",
        conversation_summary: str = "",
        recent_messages_text: str = "无历史对话",
        thread_id: str | None = None,
    ) -> str:
        if (
            recent_messages_text == "无历史对话"
            and not conversation_summary.strip()
            and not tenant_profile_summary.strip()
        ):
            return query

        fields = self._memory_prompt_fields(
            tenant_profile_summary=tenant_profile_summary,
            conversation_summary=conversation_summary,
            recent_messages_text=recent_messages_text,
        )
        chain = self.rewrite_prompt | self.llm
        with span("rag.llm.invoke", {"rag.operation": "rewrite"}):
            rewritten_query = timed_llm_invoke(
                "rewrite",
                lambda: chain.invoke({"human_input": query, **fields}),
                fallback_text=query,
                thread_id=thread_id,
            )
        rewritten_query_text = llm_output_to_text(rewritten_query)
        logger.info("rewritten query: %s", rewritten_query_text, extra=log_extra())
        if VERBOSE_RETRIEVAL:
            logger.debug("rewritten query detail: %s", rewritten_query_text, extra=log_extra())
        return rewritten_query_text or query

    def rewrite_query(self, query: str, history: ChatMessageHistory) -> str:
        chat_history = self.get_chat_history_text(history)
        return self.rewrite_query_with_memory(
            query,
            recent_messages_text=chat_history,
        )

    def generate_prompt_inputs(
        self,
        query: str,
        context: str,
        *,
        tenant_profile_summary: str = "",
        conversation_summary: str = "",
        recent_messages_text: str = "无历史对话",
    ) -> dict[str, str]:
        return {
            "human_input": query,
            "context": context,
            **self._memory_prompt_fields(
                tenant_profile_summary=tenant_profile_summary,
                conversation_summary=conversation_summary,
                recent_messages_text=recent_messages_text,
            ),
        }

    def hybrid_prompt_inputs(
        self,
        query: str,
        local_context: str,
        web_context: str,
        *,
        tenant_profile_summary: str = "",
        conversation_summary: str = "",
        recent_messages_text: str = "无历史对话",
    ) -> dict[str, str]:
        fields = self._memory_prompt_fields(
            tenant_profile_summary=tenant_profile_summary,
            conversation_summary=conversation_summary,
            recent_messages_text=recent_messages_text,
        )
        return {
            "human_input": query,
            "local_context": local_context,
            "web_context": web_context,
            **fields,
        }

    def get_chat_history_text(self, history: ChatMessageHistory) -> str:
        recent_messages = history.messages[-WINDOW_SIZE * 2 :]
        history_parts: list[str] = []
        for message in recent_messages:
            role = "Human" if message.type == "human" else "AI"
            history_parts.append(f"{role}: {message.content}")
        return "\n".join(history_parts) if history_parts else "无历史对话"

    def history_to_messages(self, history: ChatMessageHistory) -> list[Any]:
        messages: list[Any] = []
        for message in history.messages[-WINDOW_SIZE * 2 :]:
            if message.type == "human":
                messages.append(HumanMessage(content=message.content))
            else:
                messages.append(AIMessage(content=message.content))
        return messages

    def check_retrieval_quality(self, ranked: list[dict[str, Any]]) -> tuple[bool, str]:
        return should_reject(ranked)

    def get_response(self, query: str, history: ChatMessageHistory) -> str:
        rewritten_query = self.rewrite_query(query, history)
        ranked = self.retrieve_and_rank(rewritten_query)
        reject, msg = self.check_retrieval_quality(ranked)
        if reject:
            return msg
        context = self.format_context(ranked)
        chain = self.prompt | self.llm
        response = chain.invoke(
            self.generate_prompt_inputs(
                query,
                context,
                recent_messages_text=self.get_chat_history_text(history),
            )
        )
        record_and_track_llm(response, fallback_text=query)
        return llm_output_to_text(response)

    def stream_response(self, query: str, history: ChatMessageHistory) -> Iterator[dict[str, Any]]:
        """Legacy fixed pipeline; prefer graph streaming via api/chat.py."""
        yield {"type": "status", "stage": "rewrite", "node": "rewrite"}
        rewritten_query = self.rewrite_query(query, history)

        yield {"type": "status", "stage": "retrieve", "node": "retrieve"}
        ranked = self.retrieve_and_rank(rewritten_query)
        reject, reject_msg = self.check_retrieval_quality(ranked)
        if reject:
            yield {
                "type": "done",
                "content": reject_msg,
                "rewritten_query": rewritten_query,
                "route": "rag",
                "citations": [],
                "tool_calls": [],
            }
            return

        context = self.format_context(ranked)
        citations = self.extract_citations(ranked)

        yield {"type": "status", "stage": "generate", "node": "generate"}
        chain = self.prompt | self.llm
        prompt_inputs = self.generate_prompt_inputs(
            query,
            context,
            recent_messages_text=self.get_chat_history_text(history),
        )

        parts: list[str] = []
        for chunk in chain.stream(prompt_inputs):
            text = chunk_to_text(chunk)
            if not text:
                continue
            parts.append(text)
            yield {"type": "token", "content": text}

        full_response = "".join(parts).strip()
        record_and_track_llm(full_response, fallback_text=full_response or query)
        yield {
            "type": "done",
            "content": full_response,
            "rewritten_query": rewritten_query,
            "route": "rag",
            "citations": citations,
            "tool_calls": [],
        }


def rebuild_history(memory_state: list[dict[str, str]]) -> ChatMessageHistory:
    history = ChatMessageHistory()
    for item in memory_state:
        role = item.get("role")
        content = item.get("content", "")
        if role == "user":
            history.add_user_message(content)
        elif role == "assistant":
            history.add_ai_message(content)
    return history


def append_and_trim_memory(
    memory_state: list[dict[str, str]], user_text: str, assistant_text: str
) -> list[dict[str, str]]:
    memory_state = list(memory_state)
    memory_state.append({"role": "user", "content": user_text})
    memory_state.append({"role": "assistant", "content": assistant_text})
    return memory_state[-WINDOW_SIZE * 2 :]
