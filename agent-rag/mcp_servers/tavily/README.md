# mcp-tavily-server

Tavily 联网检索 MCP Server，暴露：

- `search_web_tool` — 互联网公开信息检索（需环境变量 `TAVILY_KEY`）

## 启动（stdio）

```bash
cd agent-rag
# 确保 .env 或环境中已设置 TAVILY_KEY
python mcp_servers/tavily/server.py
```

## 说明

- 本 Server 复用 `rag/tools/tavily_search.py`，与 LangGraph `web_search` 节点逻辑一致。
- 线上 RAG 主链路在本地检索失败时会**自动**调用 Tavily，无需 MCP Client。
- MCP 供 Cursor / 运维侧独立调用，或后续通过 `langchain-mcp-adapters` 接入 Agent Tool 层。
