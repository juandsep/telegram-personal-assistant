# Deploy and configuration

How to run your own Juani on GCP. Back to the [README](../README.md).

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
   reminders are skipped while it is empty) and `API_URL` (the api's URL, for
   the ICS link and the Visor), and the repository variables
   `TELEGRAM_BOT_ID` / `TELEGRAM_BOT_ID_STAGING` (the number before `:` in each
   bot token, which checks the Visor's Mini App signature). Then deploy again.

4. Set the bot's profile: the command menu, the description shown in an empty
   chat and the about text, in Spanish (default for any other language),
   English and Chinese, plus Juani's photo
   ([`docs/assets/juani-avatar.jpg`](assets/juani-avatar.jpg), the square crop
   of [`juani.png`](assets/juani.png)). Run it again after changing the texts
   in `src/assistant/i18n.py` or the avatar:

   ```bash
   TELEGRAM_BOT_TOKEN="$(gcloud secrets versions access latest --secret=assistant-bot-token)" \
     uv run python -m assistant.admin bot-profile --photo
   ```

   Owner commands (`/invitar`, `/usuarios`, `/gif`) work but are not listed.

5. Add yourself as the owner (your chat id from @userinfobot), with ADC pointed
   at the project, and enable the TTL cleanup of the dedup markers, invites,
   counters, pending confirmations and cron markers:

   ```bash
   GCP_PROJECT_ID="$PROJECT_ID" uv run python -m assistant.admin add-owner <chat_id> <nombre>
   for c in processed invites rate spend pending cron; do
     gcloud firestore fields ttls update expire_at --collection-group="$c" --enable-ttl --async
   done
   ```

6. Register the webhook and start using the bot:

   ```bash
   curl "https://api.telegram.org/bot$TOKEN/setWebhook?url=$API_URL/tg/$PATH&secret_token=$SECRET"
   ```

For `/vincular` (Google Calendar mirror), enable the Calendar API
(`calendar-json.googleapis.com`) in the project.

Every merge into `dev` deploys `assistant-api-staging` /
`assistant-worker-staging` (their own bot and Firestore database); merging
`dev` into `main` deploys production.

## Configuration

All secrets come from Secret Manager; settings from environment variables.
Local runs read the same variables from a git-ignored `.env`.

| Variable | Service | Description |
|---|---|---|
| `GCP_PROJECT_ID` | both | GCP project |
| `FIRESTORE_DATABASE` | both | Empty for `(default)`; `staging` on staging |
| `WEBHOOK_SECRET_TOKEN` | api | Secret `assistant-webhook-secret` (X-Telegram-Bot-Api-Secret-Token) |
| `WEBHOOK_PATH` | api | Secret `assistant-webhook-path` (webhook route) |
| `UPDATES_TOPIC` | api | Pub/Sub topic, default `assistant-updates` |
| `TELEGRAM_BOT_ID` | api | Number before `:` in the bot token; checks the Visor's signature |
| `TELEGRAM_BOT_TOKEN` | worker | Secret `assistant-bot-token` |
| `DEEPSEEK_API_KEY` | worker | Secret `assistant-deepseek-key` |
| `WORKER_URL` | worker | Worker Cloud Run URL, target of the reminder tasks (empty = no reminders) |
| `WORKER_SA` | worker | Service account that signs the reminder tasks' OIDC token |
| `TASKS_QUEUE` / `TASKS_LOCATION` | worker | Cloud Tasks queue (`assistant-reminders`) and region (`us-central1`) |
| `API_URL` | worker | Public api URL, for the ICS link and the Visor |
| `KMS_KEY` | worker | Cloud KMS key that encrypts iCal URLs (empty = `/conectar` refused) |
| `BACKUP_BUCKET` | worker | Daily ledger CSV and weekly JSON backup |
| `MLFLOW_TRACKING_URI` | worker | Shared MLflow server |
| `LLM_MODEL` / `LLM_BASE_URL` | worker | Default `deepseek-flash` / `https://api.deepseek.com` |
| `MAX_MSGS_PER_MINUTE` | worker | Per-chat rate limit (default 10) |
| `MAX_LLM_USD_PER_DAY` | worker | Daily LLM spend cap per chat, default 0.10 (fails closed) |
| `CONFIRM_ABOVE` | worker | Amount above which a write asks for confirmation (default 100) |
| `DEFAULT_TIMEZONE` | worker | Default `America/Panama` |

## Admin CLI

```bash
uv run python -m assistant.admin add-owner <chat_id> <nombre>   # create or promote the owner
uv run python -m assistant.admin bot-profile [--photo]          # menu, texts and photo
uv run python -m assistant.admin migrate-gifs <owner_chat_id>   # old per-user GIFs → shared catalog
```
