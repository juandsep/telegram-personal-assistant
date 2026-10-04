# Prompt for the implementation agent — personal-assistant-bot

> **Historical.** This is the prompt that drove the first implementation
> (roadmap phases 1–5). Some of it was later superseded (Sheets → Firestore
> ledger, dedicated calendar → own agenda with Cloud Tasks reminders); see the
> note at the top of [PLAN.md](../PLAN.md).

You are an engineering agent with access to the repository at
`~/Code/portfolio/botjonh`. Your job: take the Telegram bot from "template" to
"working (roadmap phases 1–5)". Do not reinvent what already exists; complete
what is missing. Where this prompt and `PLAN.md` differ, this prompt wins.

## Before you start

- `git init` if there is no repo; initial commit on `main`, create `dev` and
  work on `feat/*` per `CONTRIBUTING.md` (Conventional Commits). One commit per
  step.
- Read `PLAN.md`, `README.md`, `CONTRIBUTING.md`, `infra/main.tf` and
  `.github/workflows/deploy.yml` in full.

## Current state (already exists)

- `infra/main.tf` — native Firestore, Artifact Registry, secrets, 3 service
  accounts, WIF, Pub/Sub (updates + cron), Cloud Scheduler ×3, budget-guard.
  Cloud Run is deployed by GitHub Actions, not Terraform.
- `src/assistant/channels/base.py`, `channels/telegram.py` — ready (extended,
  see step 3).
- `src/assistant/llm/prompts/system.md` — ready (adjusted, see step 5).
- `src/assistant/config.py`, `api.py`, `worker.py`, `llm/tools.py` — skeletons.
- `.github/workflows/{ci,deploy}.yml`, `Dockerfile`, `pyproject.toml` — touch
  them only where this prompt says so.

## LLM: DeepSeek API, model `deepseek-flash`

- Endpoint: `POST https://api.deepseek.com/chat/completions` (OpenAI format),
  header `Authorization: Bearer $DEEPSEEK_API_KEY`, `stream: false`. Client
  with `httpx` (already installed). Do **not** add the `openai` SDK; **remove**
  `google-genai` from `pyproject.toml`.
- `LLM_MODEL` defaults to `deepseek-flash`. `thinking: {"type": "disabled"}`
  (less latency and fewer tokens; reasoning is not needed for simple tool
  calling). `temperature: 0.2`.
- Tools: `tools=[{"type": "function", "function": {name, description,
  parameters, "strict": true}}]`, `tool_choice: "auto"`. The response carries
  `choices[0].message.tool_calls[].function.arguments` as a **JSON string**:
  `json.loads` and then `validate_args`. Invalid JSON = rejected tool.
- Usage: `usage.prompt_cache_hit_tokens`, `prompt_cache_miss_tokens`,
  `completion_tokens`. Cost per turn with prices in config (USD per 1M tokens,
  peak rate, September 2026): `PRICE_IN_HIT=0.006`, `PRICE_IN_MISS=0.30`,
  `PRICE_OUT=1.20`.
- Context cache: automatic in DeepSeek, by prefix. Keep the system prompt and
  the tools **identical and first** in every request to hit the cache; the
  current date and time go in a short `system` message **after** the fixed
  prefix.
- Caps: `MAX_LLM_USD_PER_DAY` per chat (default 0.10) and `MAX_MSGS_PER_MINUTE`
  (default 10), in Firestore. Past them, fail closed with a short message and
  without calling the LLM.
- DeepSeek 429 or 5xx → return 5xx to the Pub/Sub push so it retries with
  backoff. Client timeout: 30 s.
- Minimal context: system prompt + the chat's last N=6 turns.

## What is MISSING (in this order)

1. **Config and infra**
   - `config.py`: split `ApiSettings` (`GCP_PROJECT_ID`,
     `WEBHOOK_SECRET_TOKEN`, `WEBHOOK_PATH`) and `WorkerSettings` (the rest).
     The api must not require secrets it does not receive. Rename `gemini_*` →
     `DEEPSEEK_API_KEY`, `LLM_MODEL`, `PRICE_IN_HIT`, `PRICE_IN_MISS`,
     `PRICE_OUT`, `MAX_LLM_USD_PER_DAY`, `MAX_MSGS_PER_MINUTE`,
     `BACKUP_BUCKET`, `DEFAULT_TIMEZONE` (default `America/Panama`).
     `confirm_above_usd` → `confirm_above` (in the user's currency).
   - `infra/main.tf`:
     - SA `webhook`: add `roles/datastore.user` and `secretAccessor` on the
       secrets the api uses (secret token and route). Today it can neither read
       them nor deduplicate.
     - Secret `assistant-gemini-key` → `assistant-deepseek-key`.
     - GCS backup bucket (uniform access, versioning, 90-day lifecycle) +
       `roles/storage.objectCreator` for the `worker` SA on that bucket.
   - `deploy.yml` and `README.md`: reflect the new names.
   - `terraform validate` and `terraform fmt -check` must pass (if `terraform`
     is installed; if not, say so in the summary).
2. **`services/state.py`** — Firestore:
   - `users/{chat_id}`: `{nombre, rol: owner|beta, moneda, zona_horaria}`.
   - `processed/{update_id}`: idempotency in a **transaction** (if it exists,
     drop it). 7-day TTL.
   - `invites/{code}`: random code (`secrets.token_urlsafe(16)`), single use,
     expires in 24 h, carries `nombre`.
   - `preferences/{chat_id}`: budget per category, currency, time zone.
   - Per-chat counters: LLM USD of the day and messages per minute.
   - `pending/{token}`: pending confirmations (inline buttons), expire in
     10 min.
   - `history/{chat_id}`: last 6 turns for context.
3. **`services/pubsub.py`** + **`api.py`** + **`worker.py`** in echo mode
   (roadmap phase 1). Extended later.
   - `api.py`: secret token + route in constant time **before** parsing;
     accepts `message` and `callback_query`; allowlist; dedup by `update_id`;
     publishes to `assistant-updates`; 200 in <300 ms.
     - Allowlist exception: `/start <code>` from an unknown chat. The api
       validates and consumes the code in a transaction, creates
       `users/{chat_id}` with role `beta` and publishes the update. Invalid
       code → 200 doing nothing. Never calls the LLM.
   - `worker.py`: decodes the push envelope, tells an `update` from a `job`,
     runs the turn, replies through the channel, logs the trace. Ack with 2xx;
     5xx to retry (LLM 429/5xx, transient errors).
   - `channels/base.py`: add optional `callback_data` and `callback_query_id`
     to `InboundMessage`.
4. **`services/sheets.py`** — **append-only** ledger (`Gastos`, `Ingresos`),
   `google-api-python-client` + ADC.
   - Columns: `fecha, monto, moneda, categoria, nota, batch_id, update_id,
     tipo` (`registro` | `reverso`).
   - Amounts with `Decimal`, rounded to 2 decimals. Never `float` on write.
   - Idempotency by `(update_id, item index)`: a retry never duplicates rows.
   - "Undo" = append `reverso` rows with a negative amount and the same
     `batch_id`. A row is never deleted or edited.
   - `resumen_finanzas` sums including reversos.
5. **`llm/tools.py`** + **`llm/client.py`**
   - One dispatch signature: `fn(ctx: ToolContext, **args) -> str`.
     `ToolContext` carries `chat_id`, `rol`, `moneda`, `zona_horaria`,
     `update_id`, `ahora`. Role checks (owner) are done by the **code**, never
     by the LLM.
   - `validate_args`: one pydantic model per tool with `extra="forbid"`.
     Amounts > 0, valid ISO dates, strict enums. An invalid argument never
     reaches the service.
   - Schema changes:
     - `registrar_gasto` takes `items: [{monto, categoria, nota?}]` + `moneda`
       + `fecha`. Several expenses per message ("pan 2, leche 3").
     - `categoria` is a **fixed enum** mapped to 50/30/20:
       - needs (necesidades): `vivienda, servicios, supermercado, transporte,
         salud, deudas`
       - wants (ocio): `restaurantes, entretenimiento, compras, viajes,
         suscripciones, otros`
       - savings (ahorro): `ahorro, inversion`
     - `agregar_beta(chat_id, nombre)` → `invitar_beta(nombre)`: returns the
       code for the owner to pass to the beta.
     - `deshacer(batch_id?)`: without an argument, undoes the chat's last
       batch.
   - If the message has no amount > 0, the LLM asks for clarification and
     nothing is written.
   - `client.py`: tool-calling loop of at most 3 rounds. Injects the current
     date and time in the user's zone into the system prompt. The user's text
     goes **only** as a `user` message, never interpolated into the system
     prompt. If the model asks for a tool outside the allowlist, it is rejected
     and logged.
   - Adjust `system.md` to the tool changes and bump `PROMPT_VERSION`.
6. **`services/budgets.py`** — budget per category from `preferences` or,
   without one, the 50/30/20 rule over the month's income. Returns the category
   with the largest excess. Pure calculation, no LLM.
7. **`services/calendar.py`** — create/list/cancel events in `CALENDAR_ID`, in
   the user's zone.
   - `recordatorio` = 15-min event with a popup reminder at `cuando`. The
     Google Calendar app notifies.
     `# ponytail: reminder via Calendar; move to Cloud Tasks if the bot must
     write on Telegram at an exact time.`
   - `cancelar_evento` and `deshacer` require a confirmation turn (`pending` +
     inline button). Same for expenses above `confirm_above`.
8. **`observability/trace.py`** — MLflow per turn: `prompt_version`, model,
   tool, latency, tokens (cache hit, cache miss, output), USD cost, validation
   result. Message text **hashed (sha256)**, never in clear.
9. **`jobs/`** — `digest` (07:30), `checkin` (21:00), `weekly` (Sunday 19:00).
   - `weekly` also runs the backup: Firestore collections to JSON in GCS, and
     the values of the `Gastos`/`Ingresos` sheets (through the Sheets API) to
     JSON in GCS.
   - Do not use Drive `files.copy`: SAs have no Drive quota.
   - Do not create a 4th Scheduler job.

## Hard rules (non-negotiable)

- Zero PII in logs: no `chat_id`, amounts, event titles, user text or LLM
  replies. Only document ids, counters and error codes.
- Append-only financial writes; deletions, cancellations and undo require a
  prior confirmation turn.
- The LLM only emits JSON validated against the schema; the code executes.
  Never URLs or code generated by the model.
- API keys only in headers, never in URLs.
- External clients (`firestore.Client`, `build("sheets", ...)`, `pubsub_v1`,
  `storage.Client`, DeepSeek's `httpx.Client`) are created **lazily, inside
  functions**, never at `import`, so `pytest` runs without credentials.
- Everything testable has tests with mocks (`respx` for DeepSeek and Telegram).
  Include tests for: missing header → 403; wrong route → 403; unknown
  `chat_id` dropped without calling the LLM; repeated `update_id` does not
  duplicate rows; tool outside the allowlist rejected; extra arguments
  rejected; invite used twice rejected; `arguments` with invalid JSON
  rejected; LLM 429 → 5xx; daily cap exceeded → the LLM is not called.

## Out of scope

- Receipt photo (multimodal) and voice (Whisper): future phase.
- Keel (`codejunkie99/keel`): a macOS desktop tool to orchestrate coding
  agents. It is developer tooling, **not** a bot dependency. Do not add it to
  the repo.

## Definition of done

```bash
cd ~/Code/portfolio/botjonh
uv sync
uv run pytest --cov --cov-fail-under=80
uv run mypy src
uv run ruff check . && uv run ruff format --check .
```

All green, and modules 1–9 exist and are wired. Do not deploy anything or apply
Terraform; leave code, tests and a final summary with what is done, what was
skipped and why.
