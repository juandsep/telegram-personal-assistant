"""GCS copies of the data in ``$BACKUP_BUCKET``.

- ``run``: weekly JSON backup to ``backup/YYYY-MM-DD/``: the Firestore
  collections plus every ledger ``movimientos`` and agenda ``eventos``
  subcollection (collection groups).
  A 90-day lifecycle rule on ``backup/`` bounds it.
- ``export_ledger``: daily CSV of yesterday's ledger writes (all chats) to
  ``ledger/mes=YYYY-MM/YYYY-MM-DD.csv``, kept forever for the BigQuery external
  table ``botjonh.ledger`` and Looker Studio. ``monto`` is USD; files written
  before the USD ledger lack the last three columns (jagged rows are allowed).
  The worker may only create objects, so an existing file means the day is
  already exported.
"""

from __future__ import annotations

import csv
import importlib
import io
import json
import logging
from datetime import datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import google.cloud.storage as storage
from google.api_core.exceptions import PreconditionFailed
from google.cloud import firestore

from assistant.config import WorkerSettings
from assistant.services import ledger

log = logging.getLogger(__name__)

COLLECTIONS = ("users", "preferences", "invites", "pending")
CSV_FIELDS = (
    "fecha", "chat_id", "tipo_mov", "categoria", "monto",
    "moneda", "nota", "batch_id", "tipo", "monto_original", "moneda_original",
    "tasa",
)  # fmt: skip


def _bucket(settings: WorkerSettings) -> Any:
    client = storage.Client(project=settings.project_id)
    return client.bucket(settings.backup_bucket)


def run(settings: WorkerSettings) -> None:
    if not settings.backup_bucket:
        log.warning("backup_skipped reason=no_bucket")
        return
    day = datetime.now(ZoneInfo(settings.default_timezone)).date().isoformat()
    db = firestore.Client(project=settings.project_id)
    objects: dict[str, Any] = {
        f"firestore/{c}.json": {d.id: d.to_dict() for d in db.collection(c).stream()}
        for c in COLLECTIONS
    }
    objects["firestore/ledger.json"] = {
        d.reference.path: d.to_dict()
        for d in db.collection_group("movimientos").stream()
    }
    objects["firestore/agenda.json"] = {
        d.reference.path: d.to_dict() for d in db.collection_group("eventos").stream()
    }
    bucket = _bucket(settings)
    for name, data in objects.items():
        # The worker may only create objects; on a retry the object from the
        # first attempt is already there, so the backup is done.
        try:
            bucket.blob(f"backup/{day}/{name}").upload_from_string(
                json.dumps(data, default=str, ensure_ascii=False),
                content_type="application/json",
                if_generation_match=0,
            )
        except PreconditionFailed:
            log.info("backup_exists object=%s", name)
    log.info("backup_done objects=%d", len(objects))


def export_ledger(settings: WorkerSettings) -> None:
    """Yesterday's writes (by ``creado``, so backdated rows and undos count)."""
    if not settings.backup_bucket:
        log.warning("ledger_export_skipped reason=no_bucket")
        return
    tz = ZoneInfo(settings.default_timezone)
    yesterday = datetime.now(tz).date() - timedelta(days=1)
    since = datetime.combine(yesterday, time(), tz)
    until = since + timedelta(days=1)
    out = io.StringIO()
    writer = csv.DictWriter(out, CSV_FIELDS, extrasaction="ignore", lineterminator="\n")
    writer.writeheader()
    rows = 0
    state = importlib.import_module("assistant.services.state")
    for chat_id in state.list_chat_ids():
        docs = ledger.query_entries(chat_id, "creado", since, until)
        for d in sorted(docs, key=lambda d: (d["fecha"], d["batch_id"])):
            category = d.get("categoria") or d.get("fuente", "")
            writer.writerow({**d, "chat_id": chat_id, "categoria": category})
            rows += 1
    if not rows:
        log.info("ledger_export_skipped reason=no_rows")
        return
    blob = _bucket(settings).blob(f"ledger/mes={yesterday:%Y-%m}/{yesterday}.csv")
    try:
        blob.upload_from_string(
            out.getvalue(), content_type="text/csv", if_generation_match=0
        )
    except PreconditionFailed:
        log.info("ledger_export_exists")
        return
    log.info("ledger_export_done rows=%d", rows)
