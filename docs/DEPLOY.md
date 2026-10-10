# Deploy and configuration

How to run your own Juani on GCP. Back to the [README](../README.md).

## Reproduce on GCP

1. Create a GCP project (globally unique id) and link it to the billing
   account, then apply the base infrastructure:

   ```bash
   gcloud auth application-default login
   cd infra
   cp terraform.tfvars.example terraform.tfvars   # set project_id, billing_account, github_repo
   # remote state bucket (set its name in the backend "gcs" block of main.tf)
   gcloud storage buckets create gs://<project_id>-tfstate --location us-central1 \
     --uniform-bucket-level-access --public-access-prevention
   gcloud storage buckets update gs://<project_id>-tfstate --versioning
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
   first deploy, set per environment both `WORKER_URL` and `API_URL` to the
   service's Cloud Run URL (`WORKER_URL` is the reminders' target and the OIDC
   audience `/push` checks; `API_URL` builds the ICS link and the Visor), and
   the repository variables `TELEGRAM_BOT_ID` / `TELEGRAM_BOT_ID_STAGING` (the
   number before `:` in each bot token, which checks the Visor's Mini App
   signature). Then deploy again, set the same URL as `service_url` /
   `service_url_staging` in `infra/terraform.tfvars` and `terraform apply` to
   create the Pub/Sub push subscriptions.

4. Set the bot's profile: the command menu, the description shown in an empty
   chat and the about text, in English (default for any other language),
   Spanish, Chinese, French and German, plus Juani's photo
   ([`docs/assets/juani-avatar.jpg`](assets/juani-avatar.jpg), the square crop
   of [`juani.png`](assets/juani.png)). Run it again after changing the texts
   in `src/assistant/i18n.py` or the avatar:

   ```bash
   TELEGRAM_BOT_TOKEN="$(gcloud secrets versions access latest --secret=assistant-bot-token)" \
     uv run python -m assistant.admin bot-profile --photo
   ```

   Owner commands (`/invitar`, `/usuarios`, `/catalogo`) work but are not listed.

5. Add yourself as the owner (your chat id from @userinfobot), with ADC pointed
   at the project, and enable the TTL cleanup of the dedup markers, invites,
   counters, pending confirmations and cron markers:

   ```bash
   GCP_PROJECT_ID="$PROJECT_ID" uv run python -m assistant.admin add-owner <chat_id> <nombre>
   for c in processed invites requests purge rate spend pending cron; do
     gcloud firestore fields ttls update expire_at --collection-group="$c" --enable-ttl --async
   done
   ```

6. Register the webhook and start using the bot:

   ```bash
   curl "https://api.telegram.org/bot$TOKEN/setWebhook?url=$API_URL/tg/$PATH&secret_token=$SECRET"
   ```

Monitoring needs nothing at runtime: `terraform apply` creates the log-based
metrics, the alert policies (mailed to `alert_email` in `terraform.tfvars`) and
the read-only `assistant-grafana` account. To explore the metrics, run the local
Grafana described in [monitoring/README.md](../monitoring/README.md).

### Weekly cost email

Grafana sees usage, not the GCP invoice, and the budget only mails when spend
crosses 50/90/100 %. A weekly cost summary comes from the billing export plus a
scheduled Looker Studio report, set up once by hand (Terraform cannot create a
billing export):

1. **Billing → Billing export → BigQuery export → Detailed usage cost**: pick
   project `jd-botjonh` and a new dataset `billing_export` (US). Data lands
   with about a day of delay; queries stay inside the BigQuery free tier.
2. In [Looker Studio](https://lookerstudio.google.com), create a report with
   the BigQuery connector on the export table
   (`billing_export.gcp_billing_export_resource_v1_*`): a time series of
   `cost` by day and a table of `cost` by `service.description`, filtered to
   the last 7 days.
3. In the report: **Share → Schedule delivery** → recipient your address,
   repeat **Weekly**, Monday morning. Each email links the report and attaches
   a PDF with cost by service and SKU.

### Google Calendar sign-in

`calendario` → Conectar → Google uses an OAuth web client, created by hand in
the console (Terraform cannot create it). Terraform enables the Calendar API
(`calendar-json.googleapis.com`) and creates the two empty secrets.

1. **APIs & Services → OAuth consent screen**: User type **External**; app name
   Juani, support and developer email; scope
   `https://www.googleapis.com/auth/calendar.events` only. Under **Audience**,
   **Publish app** (status **In production**). The app stays unverified: users
   see Google's "Google hasn't verified this app" notice (Advanced → Go to
   Juani) and at most 100 users can sign in, enough for an invite-only bot.
   ("Testing" would expire every refresh token after 7 days.)
2. **Credentials → Create credentials → OAuth client ID**: type **Web
   application**; authorized redirect URI
   `https://<service-url>/oauth/google/callback` (the `API_URL` of each
   environment, staging too: one client can hold both).
3. Store the client id and secret (the deploy mounts them, so it fails while
   they have no version):

   ```bash
   read -rs ID     && printf '%s' "$ID"     | gcloud secrets versions add assistant-google-oauth-client-id --data-file=-
   read -rs SECRET && printf '%s' "$SECRET" | gcloud secrets versions add assistant-google-oauth-client-secret --data-file=-
   ```

The refresh tokens are encrypted with the `KMS_KEY` key, so both must be set;
without either, the Google button answers "Aún no disponible".

### Reaction catalog

Terraform creates the `<project>-media` bucket: objects readable by anyone
(`roles/storage.legacyObjectReader` for `allUsers`, which allows reading a
known object but never listing the bucket) so Telegram can fetch them by URL,
and `roles/storage.objectUser` for the service account. The deploy sets
`MEDIA_BUCKET=<GCP_PROJECT_ID>-media`; no repository variable is needed. The
owner fills it from `/catalogo` in the chat (see docs/USAGE.md).

### Photos (Gemini)

Photos of meals and receipts are read by Gemini through an API key from a
separate AI Studio project (`gen-lang-client-0241526918`, named
`botjonh-gemini`; free tier, no billing). Terraform creates the empty
`assistant-gemini-key` secret; store the key once (the deploy mounts it, so it
fails while the secret has no version):

```bash
KEY_ID=$(gcloud services api-keys list --project gen-lang-client-0241526918 \
  --filter="displayName=botjonh" --format="value(uid)")
gcloud services api-keys get-key-string "$KEY_ID" --project gen-lang-client-0241526918 \
  --format="value(keyString)" | tr -d '\n' \
  | gcloud secrets versions add assistant-gemini-key --data-file=-
```

The key is restricted to `generativelanguage.googleapis.com`. Without it,
photos answer "No pude leer la foto ahora".

Every merge into `dev` deploys the `assistant-staging` service (its own bot and
Firestore database); merging `dev` into `main` deploys `assistant` to
production.

### One service

Everything runs in one public Cloud Run service. The Telegram webhook
(`/tg/<secret path>`) only verifies the update, publishes it to Pub/Sub and
acks in under 300 ms; Pub/Sub pushes it back to the same service's `/push`,
where the LLM turn runs on its own request. `/push` and `/tasks/reminder` are
public URLs too, so the app checks Google's OIDC token on them
(`src/assistant/authz.py`): issued for `WORKER_URL`, on behalf of `WORKER_SA`;
anything else gets a 403. It runs as one service account,
`assistant-worker@<project>.iam.gserviceaccount.com` (calendars shared with it
before the Google sign-in keep working).

### Migrating from two services

Deployments from before v0.4 ran `assistant-api` and `assistant-worker` (plus
`-staging`) with two service accounts. Moving to the one `assistant` service
changes the URL, so do it per environment, staging first:

1. **Grant first, with `gcloud`.** Give `assistant-worker` the webhook
   account's permissions: `roles/pubsub.publisher` on `assistant-updates` and
   `assistant-updates-staging`, and `roles/secretmanager.secretAccessor` on
   `assistant-webhook-secret` and `assistant-webhook-path`. Without them the
   new service cannot mount the webhook secrets and the deploy fails. Do not
   use `terraform apply -target=...` for this: the target pulls in
   `google_service_account.sa` and would destroy `assistant-webhook`, which
   the old services still run on. Terraform adopts these bindings later.
2. **Deploy.** A merge into `dev` (or `main`) creates `assistant-staging` (or
   `assistant`). The old services keep serving until step 5.
3. **Point the service at itself.** Set the environment's `API_URL` and
   `WORKER_URL` to the new URL, rerun the deploy, and check `/health` (200),
   `/visor` (200) and `POST /push` without a token (403).
4. **Repoint the push subscriptions** (`assistant-updates[-staging]-push`, and
   `assistant-cron-push` in production) to `<url>/push`, with
   `--push-auth-service-account=assistant-worker@…` and
   `--push-auth-token-audience=<url>`. The audience must equal `WORKER_URL`, or
   `/push` answers 403. Set the same URL as `service_url[_staging]` in
   `infra/terraform.tfvars`. The variables were renamed from `worker_url[_staging]`.
5. **Move the Telegram webhook** to `<url>/tg/<path>` with `setWebhook` and the
   same secret token. `getWebhookInfo` must show the new host and no
   `last_error_message`.
6. **Test** a quick entry, a free-text (LLM) message, `/anular 1` and, in
   production, a scheduled `tick` and a reminder.
7. **Delete the old services only when Cloud Tasks is drained.** Queued
   reminders carry the old worker URL and audience, so
   `gcloud tasks list --queue=assistant-reminders` must show none that target
   it. Until then, leave the old worker up; it costs nothing while idle.
8. **Final `terraform apply`** once both environments are migrated. It removes
   `assistant-webhook` and its grants, and adopts the bindings from step 1.
   Delete the `GCP_WEBHOOK_SA` and `MLFLOW_TRACKING_URI` repository variables.

## Configuration

All secrets come from Secret Manager; settings from environment variables.
Local runs read the same variables from a git-ignored `.env`.

| Variable | Description |
|---|---|
| `GCP_PROJECT_ID` | GCP project |
| `FIRESTORE_DATABASE` | Empty for `(default)`; `staging` on staging |
| `WEBHOOK_SECRET_TOKEN` | Secret `assistant-webhook-secret` (X-Telegram-Bot-Api-Secret-Token) |
| `WEBHOOK_PATH` | Secret `assistant-webhook-path` (webhook route) |
| `UPDATES_TOPIC` | Pub/Sub topic, default `assistant-updates` |
| `TELEGRAM_BOT_ID` | Number before `:` in the bot token; checks the Visor's signature |
| `TELEGRAM_BOT_TOKEN` | Secret `assistant-bot-token` |
| `DEEPSEEK_API_KEY` | Secret `assistant-deepseek-key` |
| `WORKER_URL` | The service's URL: reminder target and the OIDC audience of `/push` (empty = no reminders, `/push` refused) |
| `WORKER_SA` | The runtime service account: signs reminder tasks; the only caller `/push` accepts |
| `TASKS_QUEUE` / `TASKS_LOCATION` | Cloud Tasks queue (`assistant-reminders`) and region (`us-central1`) |
| `API_URL` | The service's public URL, for the ICS link and the Visor |
| `KMS_KEY` | Cloud KMS key that encrypts iCal URLs and Google refresh tokens (empty = both refused) |
| `GOOGLE_OAUTH_CLIENT_ID` | Secret `assistant-google-oauth-client-id` (empty = Google sign-in refused) |
| `GOOGLE_OAUTH_CLIENT_SECRET` | Secret `assistant-google-oauth-client-secret` |
| `GEMINI_API_KEY` | Secret `assistant-gemini-key` (empty = photos refused) |
| `GEMINI_MODEL` | Gemini model that reads photos (default `gemini-3.5-flash-lite`) |
| `BACKUP_BUCKET` | Daily ledger CSV and weekly JSON backup |
| `LLM_MODEL` / `LLM_BASE_URL` | Default `deepseek-flash` / `https://api.deepseek.com` |
| `MAX_MSGS_PER_MINUTE` | Per-chat rate limit (default 10) |
| `MAX_LLM_USD_PER_DAY` | Daily LLM spend cap per chat, default 0.10 (fails closed) |
| `CONFIRM_ABOVE` | Amount above which a write asks for confirmation (default 100) |
| `DEFAULT_TIMEZONE` | Default `America/Panama` |

## Admin CLI

```bash
uv run python -m assistant.admin add-owner <chat_id> <nombre>   # create or promote the owner
uv run python -m assistant.admin bot-profile [--photo]          # menu, texts and photo
GCP_PROJECT_ID=jd-botjonh uv run python -m assistant.admin anonymize-exports  # one-off: alias in old ledger CSVs
```
