# Roadmap: personal finance and calendar assistant (Telegram)

> **This is the original plan (phase 0).** It records the decisions and their
> reasons. The implementation evolved from it: the ledger moved from Google
> Sheets to Firestore (with a daily CSV export to BigQuery), the dedicated
> Google Calendar became the bot's own agenda in Firestore (with an optional
> Google Calendar mirror and an ICS feed), reminders became Cloud Tasks at the
> exact time, the three Scheduler jobs became one hourly `tick` in each user's
> time zone, the two Cloud Run services (`assistant-api`, `assistant-worker`)
> became one `assistant` service that keeps Pub/Sub between the webhook and the
> LLM turn, the shared MLflow gave way to Cloud Monitoring (log-based metrics,
> alerts) with a local Grafana, and the bot became Juani (Spanish, English and Chinese, a pinned
> Mini App dashboard). For how it works today, see the [README](README.md) and
> [docs/](docs/).

A Telegram bot that is your finance advisor and your calendar: it logs expenses
and income in Google Sheets, recommends budgets to save, schedules appointments
(medical, personal) in Google Calendar and reaches out proactively. Target cost
**≤ US$1/month** (LLM tokens only), with no exposure of personal data.

- **Channel:** Telegram Bot API. Free, no templates, no 24 h window.
- **Users:** you (owner) plus a few beta testers. Explicit allowlist.
- **Cloud:** GCP, reusing the infrastructure already set up in
  `portfolio-infra`.
- **Status:** plan approved = phase 0.

---

## 1. Decisions and why

| Topic | Decision | Reason |
|---|---|---|
| Channel | **Telegram Bot API** | Free, unrestricted proactive messages, set up in minutes. WhatsApp is ruled out (see §8). |
| Repo | **A single repo** `personal-assistant-bot` | One product = one repo = one GCP project (ADR 0006, one GCP project per product). Shared infrastructure already lives in `portfolio-infra`. |
| Compute | **Cloud Run**, billed per request, scale to zero | The free tier easily covers a personal bot. `min-instances=0` is mandatory. |
| Decoupling | **2 Cloud Run services + Pub/Sub** | Cloud Run does not guarantee CPU between requests: a `BackgroundTasks` is lost. Telegram retries without a 2xx. `api` acks in <300 ms, `worker` thinks and writes. |
| LLM | **DeepSeek API, `deepseek-flash`** | Cheap paid API (0.30/1M in miss, 0.006 hit, 1.20/1M out), automatic prefix cache, tool calling. Accepted risk: data is processed on DeepSeek servers (China). Minimal context is sent. |
| Observability | **Shared MLflow from `jd-portfolio-shared`** (ADR 0002, shared MLflow on Cloud Run) | Already exists, costs $0 idle. **No** own e2-micro: less ops, same cost. Message text is stored hashed. |
| Finance | **Google Sheets** (ledger) + **Firestore** (budgets, preferences) | Sheet = readable and editable on the phone. Budgets are structured per-user config → Firestore. |
| Calendar | **Dedicated Google Calendar** | Does not touch your main calendar. |
| Proactive | **Cloud Scheduler → Pub/Sub → worker** | Cloud Scheduler publishes straight to Pub/Sub: no `/cron/*` endpoints with OIDC needed. |
| Google access | **Service account** + share ONE sheet and ONE calendar | No personal OAuth refresh token. The SA only sees what you share with it. |
| Google OAuth verification (2026-10) | **Not now**: the consent screen stays published but unverified | Verification only removes the "unverified app" notice and the 100-user cap. It needs an owned domain verified in Search Console for the home, privacy and terms pages (today on `github.io`, with no root `index.html`). Revisit before opening the bot beyond invited users. Apple and Outlook use the ICS feed, which needs neither. |

Data model: **Firestore** = operational state (users, idempotency,
confirmations, preferences, budgets, LLM counters). **Sheets** = ledger
(Gastos, Ingresos). **Calendar** = events.

---

## 2. Architecture

```
Your Telegram / beta testers
      │
      ▼
[Telegram Bot API]──webhook POST──▶ [Cloud Run: assistant-api]        [Cloud Scheduler]
      ▲                                │  checks secret token                │
      │                                │  chat_id allowlist                  │ publish
      │                                │  dedup by update_id                 ▼
      │                                ▼                              [Pub/Sub: assistant-cron]
      │                          [Pub/Sub: assistant-updates]                │
      │                                │ push (OIDC)                   push (OIDC)
      │                                ▼                                 ▼
      │                          [Cloud Run: assistant-worker]
      │                                │
      └──sendMessage──────────────────┤
                                       ├─▶ DeepSeek flash (tool calling)
                                       ├─▶ Firestore   (state, users, budgets)
                                       ├─▶ Google Sheets (Gastos, Ingresos)
                                       ├─▶ Google Calendar (dedicated calendar)
                                       └─▶ Shared MLflow (tokens, latency, cost)

Secret Manager → bot token, secret token, webhook route, DeepSeek key
```

### Why two services

`assistant-api` returns 200 in <300 ms: it checks
`X-Telegram-Bot-Api-Secret-Token` in constant time, checks the allowlist,
deduplicates by `update_id` and publishes to Pub/Sub. It does not think and
does not write data. `assistant-worker` consumes, calls the LLM with the allowed
tools, writes to Sheets/Calendar/Firestore and replies. LLM latency stops being
a correctness problem.

### Services

1. **assistant-api** — webhook at `/tg/<random-route>`. 403 if the header does
   not match; drops without spending tokens if the `chat_id` is not on the
   allowlist; dedup by `update_id` in a Firestore transaction; publishes to
   `assistant-updates`.
2. **assistant-worker** — push subscriber of `assistant-updates` (user
   messages) and `assistant-cron` (proactive jobs). Calls the LLM, validates
   arguments, runs the write, replies through the Bot API, logs the trace to
   MLflow.
3. **Cloud Scheduler** — 3 jobs that publish to `assistant-cron`: morning
   summary (07:30), end of day (21:00) and weekly review (Sunday 19:00).

### Typical flow

- "I spent 45 on lunch with Ana" → worker → tool `registrar_gasto` → append to
  `Gastos` → "✓ 45 → lunch" with an undo button.
- "Book the dentist Thursday 4pm" → `crear_evento` → dedicated calendar.
- "How am I doing this month?" → `resumen_finanzas` → figures in 2 lines.
- "Where can I save?" → `recomendar_presupuesto` → category vs budget plus a
  suggestion.

### Proactive

No window or template restrictions. Three Cloud Scheduler jobs produce normal,
free messages. One initial condition: each user taps `/start` once so the bot
stores their `chat_id`.

---

## 3. User allowlist (owner + beta)

Firestore collection `users/{chat_id}`: `{nombre, rol: owner|beta, moneda,
zona_horaria}`. Only the `owner` can run `invitar_beta` and `listar_usuarios`.
A beta joins with `/start <code>` (single use, 24 h). Any `chat_id` outside the
collection is dropped **without spending tokens**. This keeps the allowlist
guarantee of the original plan and admits beta testers.

---

## 4. LLM tools (allowlist)

| Tool | Arguments | Effect |
|---|---|---|
| `registrar_gasto` | items[{monto, categoria, nota?}], moneda, fecha | append to `Gastos` |
| `registrar_ingreso` | monto, moneda, fuente, fecha, nota? | append to `Ingresos` |
| `resumen_finanzas` | periodo (hoy/mes/semana) | aggregated read of the ledger |
| `recomendar_presupuesto` | periodo (mes) | category vs budget plus a savings suggestion |
| `crear_evento` | titulo, inicio, fin?, ubicacion?, recordatorio_min? | insert into the dedicated calendar |
| `listar_agenda` | rango (hoy/manana/semana) | read the calendar |
| `cancelar_evento` | evento_id, confirmado | delete, requires prior confirmation |
| `recordatorio` | texto, cuando | event with an alert in the dedicated calendar |
| `deshacer` | batch_id? | reverso rows (requires confirmation) |
| `invitar_beta` | nombre | owner only: creates an invite code |
| `listar_usuarios` | — | owner only: lists the allowlist |

`recomendar_presupuesto` is **rule based**: the code aggregates spend by
category, compares it with the per-category budget in
`preferences/{chat_id}`, and the LLM only summarizes in ≤2 lines. Without a
configured budget, the 50/30/20 rule (needs/wants/savings) applies. This keeps
token spend low: the model does not "calculate" the budget, it only presents
it.

The system prompt and the schemas live in the repo as a versioned artifact
(`src/assistant/llm/prompts/system.md`); every change bumps the version and is
recorded in MLflow.

### Reply style (product requirement)

The system prompt enforces **very concise** replies:

- At most 2 short lines. No greetings, no closing phrases, no filler.
- Figures only when the user asks for them; rounded to 2 decimals.
- At most 1 emoji per reply; never Markdown tables (Telegram does not render
  them).
- Confirms with the result in one line: "✓ 45 → lunch".

---

## 5. Costs (verified rates, September 2026)

| Component | Free tier / rate | Cost |
|---|---|---|
| Telegram Bot API | Free | $0.00 |
| Cloud Run ×2 | 2M requests, 180k vCPU-s, 360k GiB-s free/month | $0.00 |
| Firestore | 1 GiB, 50k reads/day, 20k writes/day free | $0.00 |
| Pub/Sub ×2 topics | 10 GiB/month free | $0.00 |
| Cloud Scheduler ×3 | 3 jobs free per billing account | $0.00 |
| Secret Manager | 6 active versions, 10k accesses/month free | $0.00 |
| Google Sheets / Calendar | Free (service account) | $0.00 |
| Shared MLflow | Cloud Run scale to zero + Neon free tier | $0.00 |
| DeepSeek flash | 0.30/1M in (0.006 cached), 1.20/1M out | ~$0.5–1 |
| **Total** | | **≈ $0.5–1/month** |

Billing traps to avoid from day one:

- `min-instances=1` on Cloud Run: ends the free tier. It must be `0`.
- Static IP / SSD disk on any VM: billed. (There are no VMs in this design.)
- Egress >1 GB/month is billed. Irrelevant for a text bot.
- Budget alerts at $1 and $5 **before** deploying. Budget guard at $3.

---

## 6. Security

**Input authenticity**
- `X-Telegram-Bot-Api-Secret-Token` compared in constant time *before*
  parsing. Telegram does **not sign** the body, so the webhook route is also
  secret (`/tg/<32 random chars>`).
- `chat_id` allowlist (`users` collection). Anyone else is dropped without
  spending tokens.
- Dedup by `update_id` in a Firestore transaction (a retry never duplicates a
  row).
- Pub/Sub push to the worker with mandatory OIDC
  (`--no-allow-unauthenticated`).

**Credentials**
- Every secret in Secret Manager; zero secrets in the repo or in plain env.
- Separate service accounts: `assistant-webhook` (only `pubsub.publisher`),
  `assistant-worker` (`firestore.user` + `secretAccessor` on named secrets +
  access to ONE sheet and ONE calendar), `assistant-deploy` (GitHub WIF).
- No personal OAuth refresh token. The SA has Editor on one spreadsheet and
  write access to one dedicated calendar; never all of Drive.

**Leaks through logs / LLM**
- Zero PII in Cloud Logging (no `chat_id`, amounts or titles). Document ids and
  counters are logged. 30-day retention.
- MLflow stores the versioned prompt hash + git sha + tokens + latency + tool.
  Text is stored hashed, never in clear.
- Minimal context is sent (never the full ledger); the model emits validated
  JSON and the code executes (never URLs or code generated by the model).
- Append-only financial writes; operations above a configurable amount or event
  deletions require a confirmation turn.
- Daily LLM spend cap (USD) and messages per minute (token bucket in
  Firestore).

**At rest and backup**
- Firestore, Sheets, GCS and Calendar encrypt at rest. Weekly backup: dumps the
  collections to JSON in GCS plus a copy of the spreadsheet.
- Bot token and DeepSeek key rotated every 90 days.

---

## 7. Repository structure (a single repo)

```
personal-assistant-bot/
├── ROADMAP.md
├── README.md                 # architecture + local run + deploy
├── CONTRIBUTING.md           # branch flow (same as uplift)
├── pyproject.toml            # uv + ruff + mypy + pytest
├── Dockerfile                # one image, two entrypoints (api / worker)
├── .github/
│   ├── workflows/ci.yml      # lint, mypy, pytest (cov ≥80), detect-secrets, gitleaks, pip-audit, build
│   ├── workflows/deploy.yml  # dev→staging, main→prod, WIF, pinned SHAs
│   └── pull_request_template.md
├── infra/
│   ├── main.tf               # APIs, buckets, SA, WIF, secrets, scheduler, budget guard
│   └── terraform.tfvars.example
├── src/assistant/
│   ├── config.py             # settings from Secret Manager
│   ├── api.py                # webhook: secret token, allowlist, dedup, publish
│   ├── worker.py             # Pub/Sub consumer (updates + cron)
│   ├── channels/
│   │   ├── base.py           # common channel interface
│   │   └── telegram.py       # sendMessage, inline buttons, /start
│   ├── llm/
│   │   ├── client.py         # DeepSeek flash, spend cap
│   │   ├── tools.py          # schemas + validation (allowlist)
│   │   └── prompts/system.md # versioned prompt (concise style)
│   ├── services/
│   │   ├── sheets.py         # append-only, service account
│   │   ├── calendar.py       # dedicated calendar
│   │   ├── state.py          # Firestore: users, idempotency, preferences
│   │   └── budgets.py        # 50/30/20 rules + comparison vs budget
│   ├── jobs/                 # digest, checkin, weekly, backup
│   └── observability/trace.py# shared MLflow (hashed text)
└── tests/
```

More than one repo? **No.** One product = one repo (same rule as uplift). The
shared infrastructure (MLflow, `budget-guard` module) already lives in
`portfolio-infra` and is consumed as a module pinned by commit. The Obsidian
vault is not a product repo; it is the knowledge base.

---

## 8. Alternatives ruled out

- **WhatsApp Cloud API:** billed templates (US$0.0113/msg to Panama), 1–3
  weeks to get approved, 24 h window, a +507 SIM to keep alive. For a personal
  assistant that reaches out "when needed", Telegram removes all of that.
- **e2-micro for everything (long polling, $0):** valid and exposes no
  endpoint, but means handling restarts and patches with 1 GB shared. Plan C if
  Cloud Run caused problems.
- **Own MLflow on an e2-micro:** ruled out; the shared one already exists and
  costs $0.
- **Cloudflare Workers / AWS Lambda:** no Secret Manager/Firestore equivalents,
  and Sheets/Calendar/Gemini would sit outside the provider. More pieces, not
  fewer.

---

## 9. Roadmap

**Phase 0 — Foundations (1 h)** — Bot with @BotFather, token + secret token +
route in Secret Manager, `/start` captures `chat_id`, new GCP project, $1/$5
budgets, budget guard at $3, `git init`.
*AC:* `getMe` answers; `getWebhookInfo` shows `pending_update_count: 0`.

**Phase 1 — Echo (1 day)** — `assistant-api` (secret token + route + allowlist
+ dedup) and an `assistant-worker` that replies with fixed text.
*AC:* answers in <5 s; POST without the header → 403; a repeated `update_id`
does not duplicate.

**Phase 2 — Finance (2 days)** — SA + shared spreadsheet; `registrar_gasto`,
`registrar_ingreso`, `resumen_finanzas`, real idempotency, undo button.
*AC:* "I spent 45 on lunch" creates exactly one row; "how much have I spent
this month?" matches the sum in the Sheet.

**Phase 3 — Budget (1 day)** — `preferences` with a per-category budget,
`recomendar_presupuesto` (rules + LLM summary), 50/30/20 fallback.
*AC:* "where can I save?" returns ≤2 lines with the category most over budget.

**Phase 4 — Calendar (1 day)** — Dedicated calendar shared with the SA,
`crear_evento` / `listar_agenda`.
*AC:* "dentist Thursday 4pm" shows up in the dedicated calendar with a
reminder.

**Phase 5 — Proactive + beta (1 day)** — 3 Cloud Scheduler jobs → Pub/Sub, LLM
spend cap, `invitar_beta` / `listar_usuarios`, confirmation buttons.
*AC:* the 07:30 summary arrives on its own; a beta tester with
`/start <code>` lands on the allowlist; an unknown `chat_id` is dropped without
spending tokens.

**Phase 6 — Observability (1 day)** — Shared MLflow trace (prompt hash, tokens,
latency, cost, tool) + logging without PII.
*AC:* one trace per turn; two prompt versions compared in MLflow.

**Phase 7 — Hardening (1 day)** — Key rotation, weekly backup to GCS, log
retention, IAM review, home-made test (missing header, wrong route, unknown
`chat_id`, injection attempt).
*AC:* the four attempts fail closed and are logged.

### Backlog (2026-10)

Next, with photos read by Gemini (project `gen-lang-client-0241526918`,
named `botjonh-gemini`):

- **Meal tracking:** a photo of a plate gives estimated kcal and macros, with a
  daily total. The photo is not stored.
- **Split the check:** a photo of a receipt is split between people, and the
  bot tracks who still owes the owner money.

Pending, to review later:

- **Habits and goals:** a daily yes/no check-in in the `tick`, with streaks.
- **Savings goals:** "save 500 by December", with progress in the weekly
  summary.
- **Recurring expenses:** detect monthly charges and warn before they repeat.
- **Response latency:** some replies feel slow. Measure where a turn spends
  its time (Pub/Sub hop, cold start, LLM call, Firestore reads, Telegram send)
  from the `llm_turn` logs and Grafana, then optimize the slowest step.
  Measured 2026-10-10 over 14 days of `llm_turn`: turns without a tool p50
  1.9 s but p90 12 s (DeepSeek API spikes); turns with a tool p50 5 s (two
  LLM rounds). `calendar_status` now answers in one round. Next: compare the
  p90 against another provider (e.g. Gemini Flash-Lite, key already in place).
- **Python 3.14 (consideration):** the image stays on 3.12 and Dependabot
  ignores minor and major `python` bumps (`.github/dependabot.yml`). Before
  moving, check that every dependency ships 3.14 wheels, then update the
  Dockerfile, `.python-version` and `pyproject.toml` together.

Ruled out: voice notes, and receipt photos as a way to log expenses.

---

## 10. Risks

| Risk | Impact | Mitigation |
|---|---|---|
| Telegram does not sign webhooks | Injection if the URL is discovered | Random route + secret token + allowlist; without all three nothing is processed |
| LLM latency → retries | Duplicate rows | Fast ack + Pub/Sub + idempotency by `update_id` |
| Cloud Run freezes CPU between requests | Lost background tasks | No threads; everything through Pub/Sub |
| DeepSeek 429/5xx | Delayed replies | 5xx to the Pub/Sub push to retry with backoff; configurable model |
| Financial data processed in China | Regulatory / privacy leak | Minimal context, no names or full ledger; switch `LLM_MODEL` / provider if it starts to matter |
| Free tier broken by a wrong option | Unexpected bill | Traps in §5 + budgets + $3 budget guard |
| Financial data leak | Irreversible | Allowlist, SA (no personal OAuth), paid tier, zero PII, append-only |
| Bot blocked / `chat_id` lost | The bot cannot write to you | `chat_id` in Firestore with a weekly backup; `/start` recovers it |
