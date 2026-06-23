# agent-gateway

Agent 平台 API 网关：统一入口、反向代理 RAG 服务、多租户 RPM/TPM 限流与可观测性。

| 项 | 说明 |
|----|------|
| 技术栈 | Spring Boot 4 · Spring Cloud Gateway · Bucket4j · Redis · Java 21 |
| 默认端口 | **8080** |
| 下游服务 | [agent-rag](https://github.com/HonlinRen/agent-rag)（8081） |
| 前端 | [agent-web](https://github.com/HonlinRen/agent-web)（5173，经 Vite 代理访问本网关） |

## 功能

- **路由转发**：`/api/**`、`/health` → RAG；`/admin/rag/**` 重写后转发 RAG 管理接口
- **多租户限流**（Redis + Bucket4j，按 `X-Tenant-Id` 分桶）：
  - **RPM**：每分钟请求数
  - **TPM 输入**：LLM 路径 POST body 估算 Token
  - **TPM 输出**：流式响应累计输出 Token
- **豁免**：`/admin/**` 跳过限流；`/health` 跳过 RPM（便于探活）
- **JWT 租户绑定**（可选）：`app.jwt.enabled=true` 时校验 `Authorization: Bearer …`
- **指标**：`GET /admin/gateway/metrics` 各租户限额与通过/拒绝计数
- **链路追踪**：关联 ID 注入，OTLP 导出（默认 `http://127.0.0.1:4318`）

## 快速启动

**前置**：Redis 运行在 `localhost:6379`。

```bash
# Windows
.\mvnw.cmd spring-boot:run

# Linux / macOS
./mvnw spring-boot:run
```

验证：`GET http://localhost:8080/health`（可带 `X-Tenant-Id`）。

## 路由一览

| 路径 | 转发目标 |
|------|----------|
| `/api/**` | `http://127.0.0.1:8081` |
| `/health` | `http://127.0.0.1:8081` |
| `/admin/rag/**` | 重写为 `/admin/**` 后转发 RAG |
| `/admin/gateway/metrics` | 网关自身限流指标 |
| `/v1/**`、`/httpbin/**` | 演示上游（可替换为真实 LLM） |

## 演示租户配额

未传 `X-Tenant-Id` 时使用 `default_tenant`。

| 租户 ID | RPM/min | TPM 输入/输出/min |
|---------|---------|-------------------|
| `default_tenant` | 60 | 2000 |
| `default_tenant_test` | 2 | 2000 |
| `tenant_vip` | 10 | 10000 |
| `tenant_vip_test` | 2 | 10000 |

配额在 `src/main/resources/application.yaml` 的 `app.tenants.quotas` 中配置。

## 配置要点

`application.yaml` 中常用项：

```yaml
spring.data.redis:
  host: localhost
  port: 6379

app:
  jwt:
    enabled: false
    secret: demo-agent-gateway-secret-change-me  # 生产务必修改
  rate-limit:
    llm-path-prefixes:
      - /v1/
      - /api/chat/
```

限流触发时返回 HTTP **429**，JSON 兼容 OpenAI `rate_limit_exceeded` 格式。

## 测试

```bash
.\mvnw.cmd test
```

全栈架构与联调说明见 [agent-rag/README.md](https://github.com/HonlinRen/agent-rag/blob/master/README.md)。
