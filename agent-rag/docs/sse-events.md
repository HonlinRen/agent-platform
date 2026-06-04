# SSE 事件规范

`POST /api/chat/stream` 返回 `text/event-stream`，事件类型如下。

## 请求

```json
{
  "message": "用户问题",
  "history": [{"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}],
  "thread_id": "optional-uuid"
}
```

可选 Header：`X-Thread-Id`（与 body 中 `thread_id` 等价，body 优先）。

## 事件

### status

流水线或 LangGraph 节点进度。

```json
{
  "stage": "rewrite | retrieve | generate | router | agent | tools | direct",
  "node": "rewrite",
  "tool_name": "search_whitepaper"
}
```

`node` 与 `tool_name` 为可选扩展字段。

### token

LLM 流式输出片段。

```json
{ "content": "片段文本" }
```

### tool_call

工具调用开始或结束（Phase 1+）。

```json
{
  "name": "search_whitepaper",
  "args": { "query": "..." },
  "status": "start | end",
  "result": "..."
}
```

### done

本轮完成。

```json
{
  "content": "完整回答",
  "rewritten_query": "改写后检索词",
  "thread_id": "uuid",
  "route": "rag | direct | tool",
  "tool_calls": [],
  "run_id": "langsmith-run-id",
  "citations": [{"source": "file.pdf", "page": 3}]
}
```

### cancelled

用户调用 `POST /api/chat/stop` 或断开流后，服务端停止后续 LangGraph 节点与 token 块，下发已生成片段（可能为空）。

```json
{
  "content": "已生成片段",
  "thread_id": "uuid",
  "stopped": true,
  "request_id": "optional-request-id"
}
```

不会在同一轮中再发送 `done`。

### error

```json
{ "message": "错误说明" }
```

## 停止推理

`POST /api/chat/stop`

```json
{ "thread_id": "uuid" }
```

Header：`X-Tenant-Id`（与 stream 一致）。

响应：

```json
{ "ok": true, "cancelled": true }
```

`cancelled: false` 表示该 thread 当前无进行中的流式任务。

前端建议同时 `AbortController.abort()` 关闭 SSE 连接，并调用本接口通知服务端取消图执行。

前端应忽略未知字段与未知事件类型，保持向后兼容。
