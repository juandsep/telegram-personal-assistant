"""Bot-native agenda on Firestore, published as a private ICS feed.

Layout: ``agenda/{chat_id}/eventos/{event_id}``. Stored field names are
Spanish; the code maps them at this boundary:

- ``titulo``: title; ``inicio``/``fin``: start/end, ISO with the user's offset;
- ``inicio_utc``/``fin_utc``: start/end as timestamps for range queries;
- ``ubicacion``: location; ``recordatorio_min``: reminder minutes before;
- ``tipo``: kind (evento|recordatorio); ``estado``: status (activo|cancelado);
- ``version``: times the item was moved from Google (absent = 0), part of the
  reminder task name;
- ``creado``: server timestamp.

``event_id`` is the update_id (``{update_id}-{n}`` for another item of the same
turn), created with ``create()``: a Pub/Sub retry hits AlreadyExists and answers
the same. Cancelling sets ``estado`` and never deletes. A reminder is a Cloud
Task with a deterministic name that POSTs to the worker at the exact time.
Doc paths and task names derive from chat_ids: never log them. When the user
linked a Google Calendar (``services/gcal.py``) each create/cancel is mirrored
there too, best effort, and the hourly tick brings back moves, renames and
deletes made in Google to those mirrored items (``sync_gcal``).
"""

from __future__ import annotations

import hashlib
import importlib
import json
import logging
import os
import re
from datetime import UTC, date, datetime, time, timedelta
from functools import cache
from typing import Any
from zoneinfo import ZoneInfo

from google.api_core.exceptions import AlreadyExists, Conflict, NotFound
from google.cloud import firestore, tasks_v2
from google.cloud.firestore import FieldFilter

from assistant.config import WorkerSettings, get_worker_settings
from assistant.context import ToolContext
from assistant.i18n import t

log = logging.getLogger(__name__)

DURATION = {"evento": timedelta(minutes=60), "recordatorio": timedelta(minutes=15)}
TASKS_MAX = timedelta(days=30)  # Cloud Tasks schedules at most 30 days ahead
# ponytail: range queries look back one day, so an item longer than a day that
# started earlier is missed; add an end-time query if multi-day events appear.
LOOKBACK = timedelta(days=1)
# ponytail: the tick reads Google changes of the last 3 h each hour; applying
# one twice is a no-op. A tick gap longer than that loses the changes in it.
SYNC_WINDOW = timedelta(hours=3)
SYNC_HORIZON = timedelta(days=366)
WORKDAY = (time(8), time(20))
_ID = re.compile(r"\d{1,20}(-\d{1,2})?")


@cache
def _db() -> firestore.Client:
    return firestore.Client(
        project=os.environ.get("GCP_PROJECT_ID") or None,
        database=os.environ.get("FIRESTORE_DATABASE") or None,  # staging has its own
    )


@cache
def _tasks() -> Any:
    return tasks_v2.CloudTasksClient()


def _col(chat_id: str) -> Any:
    return _db().collection("agenda").document(chat_id).collection("eventos")


def _local(ctx: ToolContext, dt: datetime) -> datetime:
    zone = ZoneInfo(ctx.timezone)
    return dt.replace(tzinfo=zone) if dt.tzinfo is None else dt.astimezone(zone)


def _items(chat_id: str, since: datetime, until: datetime) -> list[dict]:
    """Active items of one chat overlapping [since, until), by start."""
    query = (
        _col(chat_id)
        .where(filter=FieldFilter("inicio_utc", ">=", since.astimezone(UTC) - LOOKBACK))
        .where(filter=FieldFilter("inicio_utc", "<", until.astimezone(UTC)))
    )
    docs = [{**s.to_dict(), "id": s.id} for s in query.stream()]
    active = [d for d in docs if d["estado"] == "activo" and d["fin_utc"] > since]
    return sorted(active, key=lambda d: d["inicio_utc"])


def _busy(
    ctx: ToolContext, since: datetime, until: datetime
) -> list[tuple[datetime, datetime, str]]:
    """External busy blocks (ICS feed and linked Google Calendar, which already
    skips our own mirrored events); a missing or failing source counts as none."""
    blocks = []
    for source in ("busy", "gcal"):
        try:
            mod = importlib.import_module(f"assistant.services.{source}")
            blocks += mod.busy_blocks(ctx.chat_id, since, until)
        except Exception as e:  # ImportError included: sources ship separately
            log.error("%s_failed error=%s", source, type(e).__name__)
    return [(a, b, label) for a, b, label in blocks if a < until and b > since]


def _mirror(fn: str, *args: Any) -> None:
    """Best-effort mirror into the linked Google Calendar; never raises."""
    try:
        getattr(importlib.import_module("assistant.services.gcal"), fn)(*args)
    except Exception as e:
        log.error("gcal_failed error=%s", type(e).__name__)


# --- reminders (Cloud Tasks) -----------------------------------------------------


def _queue(s: WorkerSettings) -> str:
    return (
        f"projects/{s.project_id}/locations/{s.tasks_location}/queues/{s.tasks_queue}"
    )


def task_name(s: WorkerSettings, chat_id: str, event_id: str, version: int = 0) -> str:
    """A moved item gets a new name: Cloud Tasks refuses a deleted one for days."""
    key = f"{chat_id}:{event_id}" + (f":{version}" if version else "")
    digest = hashlib.sha256(key.encode()).hexdigest()[:32]
    return f"{_queue(s)}/tasks/r-{digest}"


def _schedule(chat_id: str, event_id: str, d: dict, now: datetime) -> None:
    """Enqueue the reminder when it falls within Cloud Tasks' 30-day horizon."""
    if d.get("recordatorio_min") is None:
        return
    when = d["inicio_utc"] - timedelta(minutes=d["recordatorio_min"])
    if not now < when <= now + TASKS_MAX:
        return  # past, or too far: the daily digest enqueues it later
    s = get_worker_settings()
    if not (s.worker_url and s.worker_sa):
        log.info("reminder_skipped reason=no_worker_url")
        return
    version = d.get("version", 0)
    body: dict[str, Any] = {"chat_id": chat_id, "evento_id": event_id}
    if version:
        body["version"] = version
    task = tasks_v2.Task(
        name=task_name(s, chat_id, event_id, version),
        schedule_time=when,
        http_request={
            "http_method": tasks_v2.HttpMethod.POST,
            "url": f"{s.worker_url}/tasks/reminder",
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps(body).encode(),
            "oidc_token": {
                "service_account_email": s.worker_sa,
                "audience": s.worker_url,
            },
        },
    )
    try:
        _tasks().create_task(parent=_queue(s), task=task)
    except AlreadyExists:
        return  # same name: already enqueued
    except Exception as e:
        # ponytail: the item is saved; the next digest retries within 30 days,
        # so a reminder due before then is lost. Retry inline if that shows up.
        log.error("reminder_enqueue_failed error=%s", type(e).__name__)
        return
    log.info("reminder_enqueued")


def _delete_task(chat_id: str, event_id: str, version: int = 0) -> None:
    s = get_worker_settings()
    if not (s.worker_url and s.worker_sa):
        return
    try:
        _tasks().delete_task(name=task_name(s, chat_id, event_id, version))
    except NotFound:
        pass  # never enqueued, or already ran
    except Exception as e:  # the worker skips cancelled items anyway
        log.error("reminder_delete_failed error=%s", type(e).__name__)


def enqueue_reminders(ctx: ToolContext) -> None:
    """Digest backstop: enqueue reminders that entered the 30-day horizon."""
    # ponytail: rescans 60 days per chat daily; index a reminder field at scale.
    until = ctx.now + 2 * TASKS_MAX
    for d in _items(ctx.chat_id, ctx.now, until):
        _schedule(ctx.chat_id, d["id"], d, ctx.now)


def reminder_text(chat_id: str, event_id: str, version: int = 0) -> str | None:
    """The reminder text for an active item; None if cancelled, missing or
    moved since the task was enqueued (a stale ``version``)."""
    if not _ID.fullmatch(event_id):
        return None
    snap = _col(chat_id).document(event_id).get()
    d = snap.to_dict() if snap.exists else None
    if not d or d["estado"] != "activo" or d.get("version", 0) != version:
        return None
    return f"🛎️ {d['titulo']} {datetime.fromisoformat(d['inicio']):%H:%M}"


# --- tools -----------------------------------------------------------------------


def _save(
    ctx: ToolContext,
    kind: str,
    title: str,
    start: datetime,
    end: datetime | None,
    location: str | None,
    reminder_min: int | None,
) -> str:
    start = _local(ctx, start)
    end = _local(ctx, end) if end else start + DURATION[kind]
    data = {
        "titulo": title,
        "inicio": start.isoformat(),
        "fin": end.isoformat(),
        "inicio_utc": start.astimezone(UTC),
        "fin_utc": end.astimezone(UTC),
        "ubicacion": location or "",
        "recordatorio_min": reminder_min,
        "tipo": kind,
        "estado": "activo",
    }
    for n in range(10):
        event_id = f"{ctx.update_id}-{n}" if n else str(ctx.update_id)
        ref = _col(ctx.chat_id).document(event_id)
        try:
            ref.create({**data, "creado": firestore.SERVER_TIMESTAMP})
            log.info("agenda_write tipo=%s", kind)
        except Conflict:
            previous = ref.get().to_dict() or {}
            if (previous.get("titulo"), previous.get("inicio")) != (
                title,
                data["inicio"],
            ):
                continue  # another item of the same turn
            log.info("agenda_retry")
        _schedule(ctx.chat_id, event_id, data, ctx.now)
        _mirror("mirror_create", ctx, event_id, data)
        return f"✓ {start:%d/%m %H:%M} {title} [{event_id}]"
    raise RuntimeError("agenda_ids_exhausted")


def create_event(
    ctx: ToolContext,
    title: str,
    start: datetime,
    end: datetime | None = None,
    location: str | None = None,
    reminder_min: int | None = None,
) -> str:
    return _save(ctx, "evento", title, start, end, location, reminder_min)


def create_reminder(ctx: ToolContext, text: str, when: datetime) -> str:
    return _save(ctx, "recordatorio", text, when, None, None, 0)


def cancel_event(ctx: ToolContext, event_id: str) -> str:
    if not _ID.fullmatch(event_id):
        return t(ctx.lang, "event_not_found")
    ref = _col(ctx.chat_id).document(event_id)
    snap = ref.get()
    if not snap.exists or (snap.to_dict() or {}).get("estado") != "activo":
        return t(ctx.lang, "event_not_found")
    ref.update({"estado": "cancelado"})
    _delete_task(ctx.chat_id, event_id, (snap.to_dict() or {}).get("version", 0))
    _mirror("mirror_cancel", ctx, event_id)
    log.info("agenda_cancel")
    return t(ctx.lang, "event_cancelled")


def sync_gcal(ctx: ToolContext) -> None:
    """Hourly: upcoming items moved, renamed or deleted in the linked Google
    Calendar follow there. Google wins for those fields; never raises."""
    try:
        gcal = importlib.import_module("assistant.services.gcal")
        upcoming = {
            gcal.event_gid(ctx.chat_id, d["id"]): d
            for d in _items(ctx.chat_id, ctx.now, ctx.now + SYNC_HORIZON)
        }
        if not upcoming:
            return
        zone = ZoneInfo(ctx.timezone)
        since = ctx.now - SYNC_WINDOW
        for gid, deleted, start, end, title in gcal.changes(ctx.chat_id, since, zone):
            d = upcoming.get(gid)
            if d is None:
                continue
            ref, version = _col(ctx.chat_id).document(d["id"]), d.get("version", 0)
            if deleted:
                ref.update({"estado": "cancelado"})
                _delete_task(ctx.chat_id, d["id"], version)
                log.info("gcal_sync_cancel")
                continue
            if (start, end) != (d["inicio_utc"], d["fin_utc"]):
                _delete_task(ctx.chat_id, d["id"], version)
                moved = {
                    "inicio": start.astimezone(zone).isoformat(),
                    "fin": end.astimezone(zone).isoformat(),
                    "inicio_utc": start,
                    "fin_utc": end,
                    "version": version + 1,
                    "titulo": title or d["titulo"],
                }
                ref.update(moved)
                _schedule(ctx.chat_id, d["id"], {**d, **moved}, ctx.now)
                log.info("gcal_sync_move")
            elif title and title != d["titulo"]:
                ref.update({"titulo": title})
                log.info("gcal_sync_rename")
    except Exception as e:  # one chat's calendar never breaks the tick
        log.error("gcal_sync_failed error=%s", type(e).__name__)


def agenda_range(ctx: ToolContext, period: str) -> tuple[datetime, datetime]:
    """[start, end) in the user's zone for hoy|manana|semana (next 7 days)."""
    zone = ZoneInfo(ctx.timezone)
    day = ctx.now.astimezone(zone).date()
    start = datetime(day.year, day.month, day.day, tzinfo=zone)
    days = {"hoy": (0, 1), "manana": (1, 2), "semana": (0, 7)}.get(period)
    if days is None:
        raise ValueError("rango")
    return start + timedelta(days=days[0]), start + timedelta(days=days[1])


def agenda_lines(ctx: ToolContext, period: str) -> list[str]:
    """Compact lines ``dd/mm HH:MM title [id]``, one per item."""
    since, until = agenda_range(ctx, period)
    zone = ZoneInfo(ctx.timezone)
    return [
        f"{d['inicio_utc'].astimezone(zone):%d/%m %H:%M} {d['titulo']} [{d['id']}]"
        for d in _items(ctx.chat_id, since, until)
    ]


def list_agenda(ctx: ToolContext, period: str) -> str:
    return "\n".join(agenda_lines(ctx, period)) or t(ctx.lang, "no_events")


def conflicts(ctx: ToolContext, start: datetime, end: datetime) -> list[str]:
    """Events and external busy blocks overlapping [inicio, fin), as short lines."""
    start, end = _local(ctx, start), _local(ctx, end)
    zone = ZoneInfo(ctx.timezone)
    blocks = [
        (d["inicio_utc"], d["fin_utc"], d["titulo"])
        for d in _items(ctx.chat_id, start, end)
        if d["tipo"] == "evento"
    ]
    blocks += _busy(ctx, start, end)
    return [
        f"{label} {a.astimezone(zone):%H:%M}–{b.astimezone(zone):%H:%M}"
        for a, b, label in sorted(blocks, key=lambda b: b[0])
    ]


def free_slot_list(ctx: ToolContext, day: date) -> list[str]:
    """Free slots between 08:00 and 20:00 of ``day`` (agenda + busy blocks)."""
    zone = ZoneInfo(ctx.timezone)
    cursor = datetime.combine(day, WORKDAY[0], zone)
    end = datetime.combine(day, WORKDAY[1], zone)
    blocks = [
        (d["inicio_utc"], d["fin_utc"])
        for d in _items(ctx.chat_id, cursor, end)
        if d["tipo"] == "evento"
    ]
    blocks += [(a, b) for a, b, _ in _busy(ctx, cursor, end)]
    gaps = []
    for a, b in sorted(blocks):
        if a > cursor:
            gaps.append((cursor, min(a, end)))
        cursor = max(cursor, b)
    if cursor < end:
        gaps.append((cursor, end))
    return [
        f"{a.astimezone(zone):%H:%M}–{b.astimezone(zone):%H:%M}"
        for a, b in gaps
        if b > a
    ]


def free_slots(ctx: ToolContext, day: date) -> str:
    return ", ".join(free_slot_list(ctx, day)) or t(ctx.lang, "no_free_slots")


def week_text(ctx: ToolContext) -> str:
    """/calendario: one line per day with items in the next 7 days."""
    weekday_names = t(ctx.lang, "weekdays").split()
    since, until = agenda_range(ctx, "semana")
    zone = ZoneInfo(ctx.timezone)
    entries = [
        (d["inicio_utc"], d["titulo"]) for d in _items(ctx.chat_id, since, until)
    ]
    entries += [(a, label) for a, _, label in _busy(ctx, since, until)]
    days: dict[date, list[str]] = {}
    for start, title in sorted(entries, key=lambda e: e[0]):
        local = max(start, since).astimezone(zone)
        days.setdefault(local.date(), []).append(f"{local:%H:%M} {title}")
    lines = [
        " · ".join([f"{weekday_names[day.weekday()]} {day.day}", *items])
        for day, items in days.items()
    ]
    return "\n".join(lines) or t(ctx.lang, "empty_7_days")


# --- ICS feed (RFC 5545) ---------------------------------------------------------


def _escape(text: str) -> str:
    text = text.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,")
    return text.replace("\r\n", "\\n").replace("\n", "\\n").replace("\r", "\\n")


def _fold(line: str) -> str:
    """Fold at 75 octets without splitting a UTF-8 character."""
    parts, current, octets = [], "", 0
    for ch in line:
        n = len(ch.encode())
        if octets + n > 75:
            parts.append(current)
            current, octets = " ", 1
        current += ch
        octets += n
    parts.append(current)
    return "\r\n".join(parts)


def _utc_ics(dt: datetime) -> str:
    return dt.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")


def ics(chat_id: str, now: datetime) -> str:
    """VCALENDAR with active items from 30 days ago to 365 days ahead."""
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//botjonh//agenda//ES",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "X-WR-CALNAME:botjonh",
    ]
    since, until = now - timedelta(days=30), now + timedelta(days=365)
    for d in _items(chat_id, since, until):
        title = _escape(d["titulo"])
        lines += [
            "BEGIN:VEVENT",
            f"UID:{d['id']}@botjonh",
            f"DTSTAMP:{_utc_ics(now)}",
            f"DTSTART:{_utc_ics(d['inicio_utc'])}",
            f"DTEND:{_utc_ics(d['fin_utc'])}",
            f"SUMMARY:{title}",
        ]
        if d.get("ubicacion"):
            lines.append(f"LOCATION:{_escape(d['ubicacion'])}")
        if d.get("recordatorio_min") is not None:
            lines += [
                "BEGIN:VALARM",
                "ACTION:DISPLAY",
                f"DESCRIPTION:{title}",
                f"TRIGGER:-PT{d['recordatorio_min']}M",
                "END:VALARM",
            ]
        lines.append("END:VEVENT")
    lines.append("END:VCALENDAR")
    return "".join(f"{_fold(line)}\r\n" for line in lines)
