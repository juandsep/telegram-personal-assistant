<p align="center">
  <img src="docs/assets/juani.gif" alt="Juani" width="320">
</p>

<h1 align="center">Juani</h1>

<p align="center">
  Your expense and calendar assistant on Telegram · español · English · 中文
</p>

**Juani** (repo `telegram-personal-assistant`) is a single-user Telegram bot
that is a finance advisor and a calendar: it logs expenses and income to a
Firestore ledger, recommends budgets to save, keeps its own agenda of
appointments (medical, personal) that you subscribe to from Google, Apple or
Outlook as a private ICS feed, and sends exact-time reminders on Telegram. It
runs for one owner plus a small allowlist of beta testers, on GCP for about
$1–2/month (LLM tokens only).

- **Channel:** Telegram Bot API (webhook → Cloud Run).
- **LLM:** DeepSeek `deepseek-flash` over its HTTP API (tool calling,
  automatic prefix cache). Minimal context is sent: never the full ledger.
- **State:** Firestore (users, idempotency, preferences, budgets, the
  append-only finance ledger and the agenda).
- **Reminders:** Cloud Tasks, one task per reminder, POSTed to the worker at
  the exact time.
- **Reporting:** the ledger is exported daily as CSV to GCS; a BigQuery external
  table over those files feeds a Looker Studio dashboard, at about $0.
- **Observability:** the shared MLflow server in `jd-portfolio-shared`
  (prompt hash, tokens, latency, cost per turn; message text hashed).

## Architecture

![telegram-personal-assistant on GCP](docs/architecture/architecture.png)

One expense message (`café 2000cop`), handled without the LLM:

![One expense message](docs/architecture/expense-turn.png)

Interactive versions (theme, zoom, guided views): open
[`docs/architecture/architecture.html`](docs/architecture/architecture.html) and
[`docs/architecture/expense-turn.html`](docs/architecture/expense-turn.html)
locally. They are generated with [archify](https://github.com/tt-a1i/archify)
from the `.json` specs next to them; edit the spec and re-render instead of
editing the HTML.

Two Cloud Run services on purpose: Cloud Run does not guarantee CPU between
requests, so `assistant-api` acknowledges the webhook in under 300 ms and only
publishes to Pub/Sub; `assistant-worker` consumes, calls the LLM, writes and
replies. Idempotency by `update_id` in a Firestore transaction.

See [PLAN.md](PLAN.md) (Spanish) for the full plan, costs and roadmap.

## Stack

FastAPI, httpx (DeepSeek, Telegram), `google-cloud-*` (Firestore, Pub/Sub,
Storage, Tasks), `mlflow-skinny`, uv + ruff + mypy + pytest, Terraform, GitHub
Actions. The ICS feed is written by hand (no calendar library).

## Run locally

Requires [uv](https://docs.astral.sh/uv/) and Python 3.12.

```bash
uv sync
uv run pre-commit install
uv run pytest
uv run mypy src
uv run ruff check . && uv run ruff format --check .
```

Local runs use a `.env` (git-ignored) with the same variables as the deploy;
see [Configuration](#configuration).

## Reproduce on GCP

1. Create a GCP project (globally unique id) and link it to the billing
   account, then apply the base infrastructure:

   ```bash
   gcloud auth application-default login
   cd infra
   cp terraform.tfvars.example terraform.tfvars   # set project_id, billing_account, github_repo
   terraform init
   terraform apply
   terraform output github_variables
   ```

2. Create the bot with @BotFather and store the secrets without echoing them:

   ```bash
   read -rs TOKEN && printf '%s' "$TOKEN" | gcloud secrets versions add assistant-bot-token --data-file=- --project "$PROJECT_ID"
   openssl rand -hex 32 | tr -d '\n' | gcloud secrets versions add assistant-webhook-secret --data-file=-
   openssl rand -hex 32 | tr -d '\n' | gcloud secrets versions add assistant-webhook-path --data-file=-
   read -rs KEY   && printf '%s' "$KEY"  | gcloud secrets versions add assistant-deepseek-key --data-file=-
   ```

3. Configure GitHub: set the values from `terraform output github_variables`
   plus the environment-specific variables, then create the `staging`
   (branch `dev`) and `production` (branch `main`) environments. After the
   first deploy, set per environment `WORKER_URL` (the worker's Cloud Run URL;
   reminders are skipped while it is empty), `API_URL` (the api's URL, for
   the ICS link and the Visor) and `TELEGRAM_BOT_ID` /
   `TELEGRAM_BOT_ID_STAGING` (the number before `:` in each bot token, which
   checks the Visor's Mini App signature), then deploy again.

4. Set the bot's profile (Juani): the command menu, the description shown in
   an empty chat and the about text, in Spanish (default for any other
   language), English and Chinese, plus the profile photo
   ([`docs/assets/juani-avatar.jpg`](docs/assets/juani-avatar.jpg), the square
   crop of [`juani.png`](docs/assets/juani.png); [`juani.gif`](docs/assets/juani.gif)
   is the animated version used on this page). Run it
   again after changing the texts in `src/assistant/i18n.py`:

   ```bash
   TELEGRAM_BOT_TOKEN="$(gcloud secrets versions access latest --secret=assistant-bot-token)" \
     uv run python -m assistant.admin bot-profile --photo
   ```

   Owner commands (`/invitar`, `/usuarios`, `/gif`) work but are not listed.

5. Add yourself as the owner (your chat id from @userinfobot), with ADC
   pointed at the project. Only invited people can use the bot: the owner sends
   `/invitar <nombre>` and forwards the single-use `t.me` link (valid 24 h);
   `/usuarios` lists users with a button to revoke a beta:

   ```bash
   GCP_PROJECT_ID="$PROJECT_ID" uv run python -m assistant.admin add-owner <chat_id> <nombre>
   for c in processed invites rate spend pending cron; do
     gcloud firestore fields ttls update expire_at --collection-group="$c" --enable-ttl --async
   done
   ```

   The loop enables TTL cleanup of the dedup markers, invites, counters and
   pending confirmations.

6. Register the webhook and start using the bot:

   ```bash
   curl "https://api.telegram.org/bot$TOKEN/setWebhook?url=$API_URL/tg/$PATH&secret_token=$SECRET"
   ```

Every merge into `dev` deploys `assistant-api-staging` / `assistant-worker-staging`;
merging `dev` into `main` deploys production.

## Quick entry and editing (no LLM)

A message with exactly one amount is registered by code, without the LLM (zero
tokens): `gasto 2 usd cafe`, `2 usd cafe`, `cafe 2000cop gasto`, `2000 cop cafe`,
`cafe 5`, `$3.50 uber`, `1.234,56 cop arriendo`, `1000usd ingreso`,
`ingreso 1000 salario`, `+500 salario`. The word `ingreso` or a leading `+`
makes it income; `gasto`, a leading `-` or any other words make it an expense.
A bare amount (`5`, `5 usd`) is not guessed: the bot asks with Gasto / Ingreso
buttons and registers on the tap. The currency is an ISO code next to the amount
(USD, COP, EUR, MXN, PEN, CLP, ARS, BRL, GBP, CAD, PAB), `$` or `€`; none means
USD. The ledger converts to USD. `2,000`/`2.000` are thousands, `2,5` is 2.5.
The rest of the words are the note; a few keywords pick the category (`cafe` →
restaurantes, `uber` → transporte, `netflix` → suscripciones…), else `otros`.
Two amounts, questions, dates or times (`mañana a las 4`, `16:00`, `lunes`) go
to the LLM.

- `/ultimos`: the last 5 movements, numbered (1 = the most recent).
- `/editar <n> <monto>[moneda]`: `/editar 1 3usd`, `/editar 2 2000 cop`.
- `/anular <n>`: asks with Confirmar/Cancelar buttons, then voids it.
- **Languages**: Spanish, English and Chinese, from the `language_code` of the
  user's Telegram app (it follows the phone unless changed in Telegram), saved
  as `users.idioma` on every message that changes it. `assistant/i18n.py` holds
  every reply, the reports, the dashboard and the category names (stored keys
  stay Spanish); the LLM is told to answer in that language. Only the
  owner-only commands (`/invitar`, `/usuarios`, `/gif`) stay in Spanish. Quick
  entry knows Spanish, English and Chinese keywords for categories, and sends
  dates and questions in any of the three to the LLM.
- `/start` (also after an invite) sends the welcome from Juani and pins the
  Visor, like `/tablero`.
- Every registration answers with the entry as stored (`−12.00 USD · Lunch ·
  Restaurantes`) and how to fix it: `editar: 15 · almuerzo · restaurantes`
  (also `edit:` / `修改:`) corrects the last movement; amount, currency,
  category (by name in any language) and note, in any order. No LLM.
- `/fun` toggles GIF replies (`users.fun`, off by default): with it on, a
  registration answers with the reaction GIF instead of the text.
- `/tablero`: pins a "Visor de gastos" button in the chat and sets it as the
  chat's menu button. It opens a Telegram Mini App with the month's dashboard
  (income, spend, savings rate against the 20% target, spend by category and
  per day, last 15 movements, ← → for other months). `assistant-api` serves the
  shell at `/visor`; the page posts Telegram's signed `initData` to
  `/visor/datos`, which checks the Ed25519 signature with Telegram's public key
  and `TELEGRAM_BOT_ID` (the number before `:` in the bot token, not a secret),
  so the api never holds the bot token and the URL carries no secret.
- In free text the LLM does the same: "el último era 3 dólares, no 5".

**Reaction GIFs.** One shared catalog, curated by the owner, answers every
user: `gif_catalog/{tipo}` (`gasto`|`ingreso`) maps a clave (a gasto category
such as `restaurantes`, an ingreso fuente such as `salario`, or `general`) to
up to 20 Telegram file_ids. After each registration the bot answers with a
random GIF of the movement's categoria/fuente, else of `general`, and no text;
the text line (`−0.49 USD · café (2,000 COP)`) is only the fallback when no GIF
fits or sending it fails. Owner only (anyone else gets a one-line refusal):

- Send a GIF with the caption `gasto`, `gasto restaurantes`, `ingreso` or
  `ingreso salario` (no clave = `general`), or reply to a GIF with
  `/gif gasto restaurantes`.
- `/gif borrar` replying to a GIF removes it from every clave.
- `/gif` alone lists the counts per tipo and clave.

Telegram file_ids are per bot, so staging (its own Firestore database and bot)
and production keep separate catalogs; curate each from its own bot. Old
per-user libraries move with
`uv run python -m assistant.admin migrate-gifs <owner_chat_id>` (copies
`gifs/{owner}` into `general`).

**Scheduled messages**, each in the user's own time zone (an hourly `tick` job
in UTC picks who is due): 07:00 agenda of the day and yesterday's spend; 22:00
the day's spend ("Tus gastos hoy: …") pointing to the Visor de gastos; Sunday 22:00 that line plus
the week's spend, top categories and, against the month's income, the 20% to
save and what is left per week, in one message. The dashboard is the pinned
Visor de gastos (`/tablero`). The ledger export (daily) and the backup (Sundays) run
from 12:00 UTC: a `cron/{key}` marker records each success, and a failure is
retried at the next hourly tick without holding back anyone's message.

## Finance ledger and reporting

Firestore is the source of truth: `ledger/{chat_id}/movimientos/{doc_id}`, one
append-only document per movement with `fecha` (ISO date), `monto` (string,
2 decimals), `moneda`, `categoria` (gasto) or `fuente` (ingreso), `tipo_mov`
(`gasto`|`ingreso`), `nota`, `batch_id`, `update_id`, `tipo`
(`registro`|`reverso`) and `creado`. Doc ids make writes idempotent: gasto
`{update_id}-{i}`, ingreso `{update_id}-i0`, undo `{batch_id}-r{i}` (negative
`reverso` copies; nothing is edited or deleted).

Every day from 12:00 UTC the `tick` job exports the previous day's writes (America/Panama)
to `gs://$BACKUP_BUCKET/ledger/mes=YYYY-MM/YYYY-MM-DD.csv` with the header
`fecha,chat_id,tipo_mov,categoria,monto,moneda,nota,batch_id,tipo`. Files are
create-only and kept forever; the weekly JSON backup lives under `backup/` with a
90-day lifecycle. Sum `monto` to net out undos (`reverso` rows are negative).

Terraform creates the BigQuery external table `botjonh.ledger` over those files
(`terraform output bigquery_ledger_table`). To build the dashboard:

1. Open [lookerstudio.google.com](https://lookerstudio.google.com) → **Create** →
   **Data source** → **BigQuery** → project `jd-botjonh` → dataset `botjonh` →
   table `ledger` → **Connect**.
2. Add a calculated field `bucket` for the 50/30/20 rule:

   ```
   CASE
     WHEN categoria IN ("vivienda","servicios","supermercado","transporte","salud","deudas") THEN "necesidades"
     WHEN categoria IN ("ahorro","inversion") THEN "ahorro"
     ELSE "ocio"
   END
   ```

3. Suggested charts (filter `tipo_mov = gasto` unless noted): monthly spend
   trend (time series, `fecha` by month, SUM `monto`); spend by `categoria`
   (bar); 50/30/20 split by `bucket` (pie) next to income (`tipo_mov = ingreso`).

## Agenda

The bot keeps its own agenda in Firestore:
`agenda/{chat_id}/eventos/{evento_id}` with `titulo`, `inicio`/`fin` (ISO with
the user's offset, plus `inicio_utc`/`fin_utc` for range queries), `ubicacion`,
`recordatorio_min`, `tipo` (`evento`|`recordatorio`), `estado`
(`activo`|`cancelado`) and `creado`. The id is the Telegram `update_id`, so a
retry never duplicates; cancelling only flips `estado`.

- **Conflicts:** before scheduling, the code checks the agenda and the busy
  blocks of a connected calendar (`/conectar <url>`); on a clash it asks
  "Choca con … ¿Agendo igual?" with buttons. "¿Qué tengo libre el jueves?"
  lists free slots between 08:00 and 20:00.
- **`/calendario`** lists the next 7 days, one line per day, without calling
  the LLM: `Jue 2 · 09:00 Dentista · 16:00 Llamada banco`.
- **Reminders** are Cloud Tasks at the exact time (`inicio - recordatorio_min`,
  or `cuando` for a recordatorio), so Telegram pings you on the minute. Cloud
  Tasks schedules at most 30 days ahead; later reminders are enqueued by the
  morning digest once they are within 30 days. Cancelling deletes the task.

### Google Calendar (instant)

Share your Google Calendar with
`assistant-worker@jd-botjonh.iam.gserviceaccount.com` (Settings → your
calendar → Share with specific people → **Make changes to events**), then send
`/vincular <calendar_id>` (for a personal account the primary calendar id is
your Gmail address; `/vincular off` unlinks). From then on every create and
cancel is mirrored there within seconds, and conflicts read that calendar
directly (your own mirrored events never clash with themselves). Firestore
stays the source of truth; the mirror is best effort. Requires the Calendar API
(`calendar-json.googleapis.com`) enabled in the project.

### Subscribe from your calendar app

`/calendario enlace` replies with your private URL
(`$API_URL/ics/<token>.ics`); anyone with it can read your agenda, so
`/calendario nuevo` replaces it and revokes the old one.

- **Google Calendar (web):** Other calendars → **+** → **From URL** → paste the
  link → **Add calendar**.
- **Apple Calendar:** iPhone: Settings → Calendar → Accounts → Add Account →
  Other → Add Subscribed Calendar. Mac: File → New Calendar Subscription.
- **Outlook:** Add calendar → Subscribe from web → paste the link → Import.

Subscriptions are read-only and refreshed by the app, not pushed: Google
refreshes every ~8–24 h (Apple and Outlook let you pick an interval), so a new
appointment may take hours to show there. The Telegram reminder does not
depend on that refresh and arrives at the exact time.

## Configuration

All secrets come from Secret Manager; settings from environment variables.

| Variable | Description |
|---|---|
| `GCP_PROJECT_ID` | GCP project |
| `TELEGRAM_BOT_TOKEN` | Secret `assistant-bot-token` |
| `WEBHOOK_SECRET_TOKEN` | Secret `assistant-webhook-secret` (X-Telegram-Bot-Api-Secret-Token) |
| `WEBHOOK_PATH` | Secret `assistant-webhook-path` (webhook route) |
| `DEEPSEEK_API_KEY` | Secret `assistant-deepseek-key` |
| `WORKER_URL` | Worker Cloud Run URL, target of the reminder tasks (per environment; empty = no reminders) |
| `WORKER_SA` | Worker service account, signs the reminder tasks' OIDC token (`GCP_WORKER_SA`) |
| `TASKS_QUEUE` | Cloud Tasks queue, default `assistant-reminders` |
| `TASKS_LOCATION` | Queue region, default `us-central1` |
| `API_URL` | Public api URL, for the ICS subscription link (per environment) |
| `MLFLOW_TRACKING_URI` | Shared MLflow server |
| `LLM_MODEL` | Default `deepseek-flash` |
| `BACKUP_BUCKET` | Weekly JSON backup and daily ledger CSV (from `terraform output`) |
| `MAX_MSGS_PER_MINUTE` | Per-chat rate limit (default 10) |
| `MAX_LLM_USD_PER_DAY` | Daily LLM spend cap per chat, default 0.10 (fails closed) |

## Contributing

Changes go on a `feat/`, `fix/` or `chore/` branch cut from `dev` and merge
into `dev` through a pull request; merging `dev` into `main` releases. See
[CONTRIBUTING.md](CONTRIBUTING.md).
