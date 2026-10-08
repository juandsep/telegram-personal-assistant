<p align="center">
  <img src="docs/assets/juani.gif" alt="Juani" width="320">
</p>

<h1 align="center">Juani</h1>

<p align="center">
  Your expense and calendar assistant on Telegram · Español · English · 中文
</p>

**Juani** (repo `telegram-personal-assistant`) is a Telegram bot that logs your
expenses and income, shows your month on a pinned dashboard, recommends how to
save, and keeps your agenda with on-the-minute reminders. It runs for one owner
plus a few invited users, on GCP, for about $1–2/month (LLM tokens only).

## What Juani does

- **Logs money in one line.** `-12 lunch`, `2000 cop cafe`, `+1500 salario`
  are registered by code with zero LLM tokens; free text goes to the LLM. Each
  entry comes back as stored; `/anular 1` voids the last one to write it again.
- **Shows your month.** The pinned *Visor de gastos* opens a Telegram Mini App
  with income, spend by category and day, and the savings rate. No secret in
  the URL: Telegram signs the user in.
- **Keeps you on track.** At 22:00 it tells you what you spent today; on Sunday,
  how the week went against the 20% savings rule.
- **Runs your agenda.** Appointments and reminders in natural language,
  conflict checks, a Google Calendar mirror and a private ICS feed.
- **Reads photos.** A meal gives estimated calories and macros; a receipt is
  split between people, and `cuentas` shows who still owes you.
- **Speaks your language.** Spanish, English, Chinese, French or German, following your phone (English for any other language).
- **Has fun if you want.** `/fun` turns on reaction GIFs.

The full guide, with every command and example, is in the documentation below.

## How it works

![telegram-personal-assistant on GCP](docs/architecture/architecture.png)

One Cloud Run service, scaled to zero. The Telegram webhook only verifies the
update, publishes it to Pub/Sub and acks in under 300 ms; Pub/Sub pushes it
back to the same service, which calls the LLM (DeepSeek, tool calling), writes
to Firestore and replies on its own request. Reminders are Cloud Tasks; reports
run from an hourly Cloud Scheduler job. Cloud Monitoring collects request and
LLM metrics and mails alerts, always on; a local Grafana explores them
([monitoring/](monitoring/README.md)). Interactive diagrams live
in [`docs/architecture/`](docs/architecture/).

## Documentation

| Document | What it covers |
|---|---|
| [docs/USAGE.md](docs/USAGE.md) | Logging, corrections, dashboard, reports, GIFs, agenda, languages, commands |
| [docs/DATA.md](docs/DATA.md) | Ledger model, CSV export and backup, Looker Studio, agenda and other collections |
| [ROADMAP.md](ROADMAP.md) | The original plan: decisions, architecture, costs, security, roadmap |

## Run locally

Requires [uv](https://docs.astral.sh/uv/) and Python 3.12.

```bash
uv sync
uv run pre-commit install
uv run pytest
uv run mypy src
uv run ruff check . && uv run ruff format --check .
```

Local runs read a git-ignored `.env` with the same variables as the deploy (see
[docs/DEPLOY.md](docs/DEPLOY.md#configuration)).

**Stack:** FastAPI, httpx (DeepSeek, Telegram), `google-cloud-*` (Firestore,
Pub/Sub, Storage, Tasks, KMS), Cloud Monitoring + Grafana, uv + ruff + mypy +
pytest, Terraform, GitHub Actions.

## Deploy

Juani runs on GCP: Terraform for the base infrastructure, GitHub Actions for
the two Cloud Run services (`dev` deploys staging, `main` deploys production).
Step by step, the bot profile, every configuration variable and the admin CLI:
see [docs/DEPLOY.md](docs/DEPLOY.md).

## Contributing

Changes go on a `feat/`, `fix/` or `chore/` branch cut from `dev` and merge
into `dev` through a pull request; merging `dev` into `main` releases. See
[CONTRIBUTING.md](CONTRIBUTING.md).
