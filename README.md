# agent-platform

全栈 Agent 平台 Monorepo：React 前端 + Spring Cloud Gateway + FastAPI / LangGraph RAG 后端。

## 架构概览

```
agent-web (:5173)  →  agent-gateway (:8080)  →  agent-rag (:8081)
                              ↓                        ↓
                           Redis                   Chroma / MySQL / DashScope
```

| 目录 | 技术栈 | 职责 |
|------|--------|------|
| [agent-web](agent-web/) | React 19 + Vite + TypeScript | 聊天 UI、会话管理、管理看板、SSE 流式展示 |
| [agent-gateway](agent-gateway/) | Spring Boot 4 + Spring Cloud Gateway | JWT 租户、RPM/TPM 限流、路由代理、可观测性 |
| [agent-rag](agent-rag/) | FastAPI + LangGraph + Chroma | RAG 检索、重排序、工具调用、对话持久化 |

请求路径：浏览器访问前端 → Vite 将 `/api` 代理到网关 `8080` → 网关转发到 RAG `8081`。

## 环境要求

- **JDK 21**（gateway）
- **Python 3.11+**（rag）
- **Node.js 18+**（web）
- **Redis**（网关限流、RAG checkpoint / 指标）
- **MySQL**（RAG 会话持久化）
- **Chroma**（向量库，默认 `127.0.0.1:8000`）
- **DashScope API Key**（通义千问 / Embedding）
- 可选：**Docker**（[观测栈](agent-rag/deploy/observability/README.md)：Prometheus + Grafana + Tempo）

## 配置

各子项目复制环境变量模板后按需修改，**切勿将 `.env` 提交到 Git**：

```bash
# agent-rag
cp agent-rag/.env.example agent-rag/.env
# 必填：DASHSCOPE_API_KEY、MySql_Password 等

# agent-web（开发环境通常无需改）
cp agent-web/.env.example agent-web/.env.development
```

本地 PDF 与 DocMind 解析结果请放在 `agent-rag/doc/`、`agent-rag/doc_result/`（已在 gitignore 中，仅本地使用）。

## 启动顺序

先启动基础设施（Redis、MySQL、Chroma），再按网关 → RAG → 前端顺序启动。

### 0. 基础设施

| 服务 | 默认地址 |
|------|----------|
| Redis | `127.0.0.1:6379` |
| MySQL | `127.0.0.1:3306`（库名见 `agent-rag/.env.example`） |
| Chroma | `127.0.0.1:8000` |

### 1. agent-gateway（端口 8080）

```powershell
cd agent-gateway
.\mvnw.cmd spring-boot:run
```

健康检查：`http://127.0.0.1:8080/actuator/health`

### 2. agent-rag（端口 8081）

```powershell
cd agent-rag
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python api_server.py
```

健康检查：`http://127.0.0.1:8081/health`

### 3. agent-web（端口 5173）

```powershell
cd agent-web
npm install
npm run dev
```

浏览器打开：`http://localhost:5173`（API 经 Vite 代理到网关 `8080`）。

### 可选：本地观测栈

```bash
cd agent-rag/deploy/observability
docker compose up -d
```

- Grafana：`http://localhost:3000`（默认 `admin` / `admin`）
- Prometheus：`http://localhost:9090`

## 安全说明

- 生产环境请修改 gateway 的 JWT secret（勿使用 `demo-agent-gateway-secret-change-me`）。
- `doc/`、`doc_result/` 可能含云服务临时 URL，仅保留在本地。
- 更完整的架构说明见 [agent-rag/README.md](agent-rag/README.md)。

## License

Private / 学习用途 — 按你方需要补充许可证。
