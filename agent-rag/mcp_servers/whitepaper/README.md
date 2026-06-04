# mcp-whitepaper-server

汽车安全白皮书 MCP Server，暴露：

- `search_whitepaper`
- `get_chunk_by_source`
- `list_collection_stats`

## 启动（stdio）

```bash
cd agent-rag
python mcp_servers/whitepaper/server.py
```

agent-rag 侧设置：

```env
MCP_ENABLED=true
MCP_WHITEPAPER_COMMAND=python mcp_servers/whitepaper/server.py
```
