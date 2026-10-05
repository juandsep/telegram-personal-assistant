"""The one Cloud Run service (``assistant``).

Public routes (``api.py``): the Telegram webhook, which only verifies, dedups,
publishes to Pub/Sub and acks in under 300 ms; the Visor Mini App; the ICS
feed. Google-only routes (``worker.py``, behind ``authz``): the Pub/Sub push
that runs the LLM turn on its own request, and the Cloud Tasks reminders.
Pub/Sub keeps the slow work off the webhook, so one service is enough.
"""

from __future__ import annotations

from fastapi import FastAPI

from assistant import api, worker

app = FastAPI(title="assistant")
app.include_router(api.router)
app.include_router(worker.router)
