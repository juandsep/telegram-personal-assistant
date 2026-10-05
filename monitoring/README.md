# Monitoring

Juani's monitoring lives in **Google Cloud Monitoring** and is always on: Cloud
Run's built-in request metrics, plus log-based metrics from the service's logs,
and email alerts for production (all in
[`infra/monitoring.tf`](../infra/monitoring.tf)). This folder adds a **local
Grafana** to explore them. It only reads, so stopping it changes nothing: the
bot keeps running, the metrics keep being collected, and the alerts keep
firing.

## What is collected

| Series | Source |
|---|---|
| Requests by status class, latency (p50/p95/p99), instances | Cloud Run built-in metrics |
| `llm_turns`, `llm_latency_ms`, `llm_cost_usd`, `llm_tokens_out` | The `llm_turn` log line of each LLM turn (`src/assistant/observability/trace.py`) |
| `llm_rejected` | LLM turns with a rejected tool call |
| `job_failed` | Scheduled job runs where some chat failed (`job_done ... failed=N`) |

Alerts (production service `assistant`, mailed to `alert_email`): more than 5
responses with 5xx in 5 min; p99 latency above 25 s for 10 min (LLM turns take
seconds by design); any failed job run in an hour; more than 3 turns with
rejected tool calls in an hour.

## Run Grafana

Requires Docker and `gcloud` authenticated on the project.

```bash
monitoring/grafana-key.sh                       # once: read-only key into monitoring/secrets/ (git-ignored)
docker compose -f monitoring/docker-compose.yml up -d
open http://localhost:3000                      # dashboard "Juani · assistant service"
docker compose -f monitoring/docker-compose.yml down
```

The **Service** selector switches between `assistant` (production) and
`assistant-staging`. The dashboard is code
([`grafana/dashboards/assistant.json`](grafana/dashboards/assistant.json)):
edit it there, not only in the UI.

The key belongs to `assistant-grafana`, which only has `roles/monitoring.viewer`.
To revoke it, list and delete the account's keys with
`gcloud iam service-accounts keys list|delete`.
