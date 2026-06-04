# Local Observability Stack

Prometheus + Grafana + Tempo + OTel Collector for agent-gateway and agent-rag.

## Start (Windows / macOS / Linux)

```bash
cd deploy/observability
docker compose up -d
```

Ensure **agent-rag** (`8081`) and **agent-gateway** (`8080`) are running on the host before scraping.

## Endpoints

| Service | URL |
|---------|-----|
| Grafana dashboard | http://localhost:3000/d/agent-observability (login `admin` / `admin`) |
| Grafana home | http://localhost:3000 |
| Prometheus | http://localhost:9090 |
| Tempo | http://localhost:3200 |
| OTLP HTTP | http://localhost:4318 |

## App configuration

Ensure gateway and rag export traces to `http://127.0.0.1:4318` and expose metrics on:

- Gateway: `http://localhost:8080/actuator/prometheus`
- RAG: `http://localhost:8081/metrics`

Prometheus scrapes `host.docker.internal:8080` and `:8081` from inside Docker (Windows/macOS).

### Human-readable timestamps on `/metrics`

Raw Prometheus text still uses Unix floats for `_created` and gauge values. RAG adds:

- Top-of-body comments: `# scrape_time_utc:` / `# process_started_utc:`
- Response headers: `X-Metrics-Scrape-At`, `X-Process-Started-At`
- Metric `rag_scrape_info` with ISO8601 labels

Example:

```bash
curl -I http://127.0.0.1:8081/metrics
curl -s http://127.0.0.1:8081/metrics | head -5
```

For time-series charts, use Grafana (not the raw text endpoint).

## Grafana dashboard

Open **Agent Observability** (`uid=agent-observability`). Top row shows:

- Last metrics scrape (from `rag_metrics_scrape_unixtime_seconds`)
- Process uptime
- Build version (`rag_build_info`)
- Chat / LLM request rates

Lower panels: p95 latencies, gateway rate limits, tool calls, retrieval scores.

## Verify

1. Prometheus → Status → Targets: `agent-rag` and `agent-gateway` should be **UP**.
2. Send a few chat requests through gateway.
3. Grafana → **Agent Observability**: stat panels and timeseries should show data.
4. Grafana → Explore → Tempo: search by `X-Request-Id` or trace ID from SSE `run_id`.
5. Prometheus query: `rag_node_duration_seconds_bucket` should have samples.

## agent-web admin links

The web admin page links to Grafana/Prometheus when `VITE_GRAFANA_URL` / `VITE_PROMETHEUS_URL` are set (defaults to localhost URLs above).
