# agent-web

Agent 平台前端：RAG 聊天 UI、多租户切换、SSE 流式展示与管理看板。

| 项 | 说明 |
|----|------|
| 技术栈 | React 19 · TypeScript · Vite 8 · Tailwind CSS 4 |
| 默认端口 | **5173** |
| 上游依赖 | [agent-gateway](https://github.com/HonlinRen/agent-gateway)（8080）→ [agent-rag](https://github.com/HonlinRen/agent-rag)（8081） |

## 功能

- **`/`** 智能问答：多会话、SSE 流式回复、引用溯源、Agent 工具链路与联网检索展示
- **`/admin`** 管理看板：RAG / Gateway 指标、问答耗时分布、用户画像
- **多租户**：请求头携带 `X-Tenant-Id`，429 限流友好提示
- **JWT（可选）**：聊天页可填写 Bearer Token，供网关 JWT 鉴权联调

## 快速启动

```bash
npm install
npm run dev
```

浏览器打开 http://localhost:5173

开发模式下，Vite 将 API 代理到网关（`vite.config.ts`）：

| 前端路径 | 代理目标 |
|----------|----------|
| `/api` | `http://127.0.0.1:8080` |
| `/health` | `http://127.0.0.1:8080` |
| `/admin/gateway`、`/admin/rag` | `http://127.0.0.1:8080` |

因此通常**无需**设置 `VITE_API_BASE_URL`；直连 RAG 调试时可设为 `http://127.0.0.1:8081`。

## 配置

复制 `.env.example` 为 `.env`（可选，观测链接等）。

知识库展示由 `config/knowledge-bases.json` 控制：

```json
{
  "visibleInChat": ["semiconductor"],
  "defaultChatCollection": "semiconductor"
}
```

名称与描述见 `src/constants/knowledgeBases.ts`。

## 推荐联调顺序

1. Redis（6379）→ agent-rag（8081）→ agent-gateway（8080）→ **本仓库**（5173）
2. 聊天页显示「后端在线」、`/admin` 能加载双服务指标即表示联调成功

全栈架构与接口说明见 [agent-rag/README.md](https://github.com/HonlinRen/agent-rag/blob/master/README.md)。

## 常用命令

```bash
npm run dev      # 开发
npm run build    # 构建
npm run preview  # 预览构建产物
npm run lint     # ESLint
```
