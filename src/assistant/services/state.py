"""Firestore state: users, dedup, invites, counters, pending confirmations.

Stored field names are Spanish (nombre = name, rol = role, moneda = currency,
zona_horaria = time zone, idioma = language, presupuesto = budget); the code
maps them at this boundary.

Collections (Firestore native):

- ``users/{chat_id}``: nombre, rol (owner|beta), moneda (display currency:
  USD|EUR|GBP|COP|CNY, /moneda; the ledger stays in USD), zona_horaria (unset until
  /moneda guesses it, the Mini App sends the phone's or /zona sets it; readers
  fall back to the default zone), idioma (es|en|zh|fr|de, from the Telegram
  app), fun (reaction images, /fun), last_batch.
- ``processed/{update_id}``: dedup marker; ``expire_at`` drives a 7-day TTL.
- ``invites/{code}``: nombre, used, ``expire_at`` (24 h, single use).
- ``rate/{chat_id}_{minute}``: messages in that minute.
- ``spend/{chat_id}_{day}``: LLM USD that UTC day, a Decimal stored as string.
- ``preferences/{chat_id}``: presupuesto por categoría, etc.
- ``pending/{token}``: chat_id, action, ``expire_at`` (10 min).
- ``history/{chat_id}``: last turns, each ``{"messages": [...]}`` (Firestore has
  no nested arrays).
- ``oauth_states/{token}``: chat_id, ``expire_at`` (10 min, single use): the
  ``state`` of a Google sign-in started from Telegram.
- ``ics_tokens/{token}``: chat_id of a private ICS feed; ``users.ics_token``
  points back so the link can be shown again or rotated. Never log tokens.
- ``comidas/{chat_id}/registros`` and ``cuentas/{chat_id}/divisiones``: meals
  and split checks read from photos (see ``assistant.services.photos``).
- ``media/{id}``: the reaction catalog (see ``assistant.services.media``).

Set a Firestore TTL policy on ``expire_at`` for processed, invites, rate, spend,
pending and oauth_states. Doc ids contain chat_ids: never log them.
"""

from __future__ import annotations

import os
import re
import secrets
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from functools import cache
from typing import Any

from google.cloud import firestore

from assistant.context import ToolContext
from assistant.i18n import t
from assistant.observability.timing import timed

HISTORY_TURNS = 6
PENDING_TTL = timedelta(minutes=10)
INVITE_TTL = timedelta(hours=24)
PROCESSED_TTL = timedelta(days=7)
REQUEST_TTL = timedelta(days=7)  # a pending access request
REJECT_WAIT_DAYS = 10  # a rejected chat may ask again after this
MAX_USERS = 100
REVOKED_PURGE_DAYS = 30  # a revoked user's data is erased after this
INACTIVE_DAYS = 60  # a beta silent this long loses data and access
INACTIVE_WARN_DAYS = 53  # ...and is warned on this day
_TOKEN = re.compile(r"[A-Za-z0-9_-]{22}")  # secrets.token_urlsafe(16)
_ICS_TOKEN = re.compile(r"[A-Za-z0-9_-]{32}")  # secrets.token_urlsafe(24)


@cache
def _db() -> firestore.Client:
    return firestore.Client(
        project=os.environ.get("GCP_PROJECT_ID") or None,
        database=os.environ.get("FIRESTORE_DATABASE") or None,  # staging has its own
    )


def _doc(collection: str, doc_id: str) -> Any:
    return _db().collection(collection).document(doc_id)


def _now() -> datetime:
    return datetime.now(UTC)


def _data(snap: Any) -> dict | None:
    return snap.to_dict() if snap.exists else None


# --- users -------------------------------------------------------------------


def get_user(chat_id: str) -> dict | None:
    return _data(_doc("users", chat_id).get())


def upsert_user(
    chat_id: str,
    name: str,
    role: str,
    currency: str = "USD",
    timezone: str = "America/Panama",
) -> None:
    _doc("users", chat_id).set(
        {"nombre": name, "rol": role, "moneda": currency, "zona_horaria": timezone},
        merge=True,
    )


def cron_done(key: str) -> bool:
    return _doc("cron", key).get().exists


def mark_cron(key: str) -> None:
    _doc("cron", key).set({"expire_at": _now() + timedelta(days=30)})


def set_fun(chat_id: str, fun: bool) -> None:
    _doc("users", chat_id).set({"fun": fun}, merge=True)


def set_weekly(chat_id: str, on: bool) -> None:
    """The Sunday spending summary on or off."""
    _doc("users", chat_id).set({"resumen_semanal": on}, merge=True)


def set_lang(chat_id: str, lang: str) -> None:
    _doc("users", chat_id).set({"idioma": lang}, merge=True)


def set_timezone(chat_id: str, tz: str) -> None:
    _doc("users", chat_id).set({"zona_horaria": tz}, merge=True)


# A first guess of the time zone from the currency, until the phone's arrives.
TIMEZONE_BY_CURRENCY = {
    "COP": "America/Bogota",
    "EUR": "Europe/Madrid",
    "GBP": "Europe/London",
    "CNY": "Asia/Shanghai",
    "USD": "America/New_York",
}


def set_currency(chat_id: str, currency: str) -> None:
    """The display currency; a missing or old-default zone gets a first guess."""
    ref = _doc("users", chat_id)
    data = {"moneda": currency}
    if (_data(ref.get()) or {}).get("zona_horaria") in (None, "", "America/Panama"):
        data["zona_horaria"] = TIMEZONE_BY_CURRENCY[currency]
    ref.set(data, merge=True)


def list_chat_ids() -> list[str]:
    return [snap.id for snap in _db().collection("users").stream()]


def set_last_batch(chat_id: str, batch_id: str) -> None:
    _doc("users", chat_id).set({"last_batch": batch_id}, merge=True)


def mark_seen(chat_id: str, day: str) -> None:
    """The user's last active day (ISO date in their zone), for /usuarios."""
    _doc("users", chat_id).set({"ultimo_uso": day}, merge=True)


def last_batch(chat_id: str) -> str | None:
    user = get_user(chat_id) or {}
    return user.get("last_batch")


def get_preferences(chat_id: str) -> dict:
    return _data(_doc("preferences", chat_id).get()) or {}


# --- dedup and invites (transactions) ------------------------------------------


@firestore.transactional
def _claim(tx: Any, ref: Any, data: dict) -> bool:
    if ref.get(transaction=tx).exists:
        return False
    tx.set(ref, data)
    return True


def mark_processed(update_id: int) -> bool:
    """True if the update is new. A retried update returns False."""
    ref = _doc("processed", str(update_id))
    return _claim(_db().transaction(), ref, {"expire_at": _now() + PROCESSED_TTL})


def unmark_processed(update_id: int) -> None:
    """Undo mark_processed when publishing failed, so Telegram's retry lands."""
    _doc("processed", str(update_id)).delete()


@firestore.transactional
def _redeem(tx: Any, invite: Any, user: Any) -> bool:
    data = _data(invite.get(transaction=tx))
    if not data or data.get("used") or data["expire_at"] <= _now():
        return False
    tx.update(invite, {"used": True})
    tx.set(
        user,
        {
            "nombre": data["nombre"],
            "rol": "beta",
            "moneda": "USD",
        },
    )
    return True


def redeem_invite(code: str, chat_id: str) -> bool:
    """Consume a single-use invite and create the beta user. False if invalid."""
    if not _TOKEN.fullmatch(code):
        return False
    return _redeem(_db().transaction(), _doc("invites", code), _doc("users", chat_id))


# --- access requests ---------------------------------------------------------


@firestore.transactional
def _request(tx: Any, req: Any, day: Any, name: str, lang: str) -> str:
    data = _data(req.get(transaction=tx))
    if data and data["expire_at"] > _now():
        return "pending" if data["status"] == "pending" else "wait"
    if day.get(transaction=tx).exists:
        return "today"
    tx.set(
        req,
        {
            "nombre": name,
            "idioma": lang,
            "status": "pending",
            "expire_at": _now() + REQUEST_TTL,
        },
    )
    tx.set(day, {"expire_at": _now() + timedelta(days=2)})
    return "sent"


def request_access(chat_id: str, name: str, lang: str) -> str:
    """A stranger's /start: sent | pending | wait (rejected lately) | today
    (the one request a day is taken) | full (MAX_USERS reached)."""
    if len(list_chat_ids()) >= MAX_USERS:
        return "full"
    day = _doc("requests", f"day-{_now().date().isoformat()}")
    return _request(_db().transaction(), _doc("requests", chat_id), day, name, lang)


def _pending_request(chat_id: str) -> dict | None:
    data = _data(_doc("requests", chat_id).get())
    if not data or data["status"] != "pending" or data["expire_at"] <= _now():
        return None
    return data


def accept_request(chat_id: str) -> dict | None:
    """Create the beta from a pending request; None if there is none."""
    if (data := _pending_request(chat_id)) is None:
        return None
    _doc("users", chat_id).set(
        {
            "nombre": data["nombre"],
            "rol": "beta",
            "moneda": "USD",
            "idioma": data["idioma"],
        }
    )
    _doc("requests", chat_id).delete()
    return data


def reject_request(chat_id: str) -> dict | None:
    """Block the chat from asking again for REJECT_WAIT_DAYS."""
    if (data := _pending_request(chat_id)) is None:
        return None
    _doc("requests", chat_id).set(
        {"status": "rejected", "expire_at": _now() + timedelta(days=REJECT_WAIT_DAYS)},
        merge=True,
    )
    return data


def owner_chat_id() -> str | None:
    return next((i for i, u in all_users() if u.get("rol") == "owner"), None)


# --- counters ------------------------------------------------------------------


@firestore.transactional
def _bump(tx: Any, ref: Any, limit: int, expire_at: datetime) -> bool:
    count = (_data(ref.get(transaction=tx)) or {}).get("n", 0)
    if count >= limit:
        return False
    tx.set(ref, {"n": count + 1, "expire_at": expire_at})
    return True


def check_rate(chat_id: str, limit_per_minute: int) -> bool:
    """True if this message is allowed within the per-minute limit."""
    now = _now()
    ref = _doc("rate", f"{chat_id}_{now:%Y%m%d%H%M}")
    return _bump(_db().transaction(), ref, limit_per_minute, now + timedelta(hours=1))


def _spend_ref(chat_id: str) -> Any:
    return _doc("spend", f"{chat_id}_{_now():%Y%m%d}")


def llm_spend_today(chat_id: str) -> Decimal:
    data = _data(_spend_ref(chat_id).get()) or {}
    return Decimal(data.get("usd", "0"))


@firestore.transactional
def _add(tx: Any, ref: Any, usd: Decimal) -> None:
    data = _data(ref.get(transaction=tx)) or {}
    total = Decimal(data.get("usd", "0")) + usd
    tx.set(ref, {"usd": str(total), "expire_at": _now() + timedelta(days=2)})


def add_llm_spend(chat_id: str, usd: Decimal) -> None:
    _add(_db().transaction(), _spend_ref(chat_id), usd)


# --- pending confirmations -----------------------------------------------------


def create_pending(chat_id: str, action: dict) -> str:
    token = secrets.token_urlsafe(16)
    _doc("pending", token).set(
        {"chat_id": chat_id, "action": action, "expire_at": _now() + PENDING_TTL}
    )
    return token


@firestore.transactional
def _pop(tx: Any, ref: Any, chat_id: str) -> dict | None:
    data = _data(ref.get(transaction=tx))
    if not data or data.get("chat_id") != chat_id:
        return None
    tx.delete(ref)
    return data["action"] if data["expire_at"] > _now() else None


def pop_pending(chat_id: str, token: str) -> dict | None:
    """Single-use: returns the action once, only to the chat that created it."""
    if not _TOKEN.fullmatch(token):
        return None
    return _pop(_db().transaction(), _doc("pending", token), chat_id)


# --- Google sign-in state -------------------------------------------------------


def create_oauth_state(chat_id: str) -> str:
    token = secrets.token_urlsafe(16)
    _doc("oauth_states", token).set(
        {"chat_id": chat_id, "expire_at": _now() + PENDING_TTL}
    )
    return token


@firestore.transactional
def _take(tx: Any, ref: Any) -> str | None:
    data = _data(ref.get(transaction=tx))
    if not data:
        return None
    tx.delete(ref)
    return data["chat_id"] if data["expire_at"] > _now() else None


def consume_oauth_state(token: str) -> str | None:
    """Single-use: the chat that started the sign-in, once; None if bogus or
    expired."""
    if not _TOKEN.fullmatch(token):
        return None
    return _take(_db().transaction(), _doc("oauth_states", token))


# --- history -------------------------------------------------------------------


def get_history(chat_id: str) -> list[dict]:
    with timed("firestore.get_history"):
        turns = (_data(_doc("history", chat_id).get()) or {}).get("turns", [])
    return [m for turn in turns for m in turn["messages"]]


def append_history(chat_id: str, messages: list[dict]) -> None:
    ref = _doc("history", chat_id)
    with timed("firestore.append_history"):
        turns = (_data(ref.get()) or {}).get("turns", [])
        turns = [*turns, {"messages": messages}][-HISTORY_TURNS:]
        ref.set({"turns": turns})


# --- ICS feed tokens ------------------------------------------------------------


def ics_token(chat_id: str, rotate: bool = False) -> str:
    """The chat's feed token, created if missing; rotate revokes the old one."""
    user = _doc("users", chat_id)
    current = (_data(user.get()) or {}).get("ics_token")
    if current and not rotate:
        return str(current)
    if current:
        _doc("ics_tokens", current).delete()
    token = secrets.token_urlsafe(24)
    _doc("ics_tokens", token).set({"chat_id": chat_id})
    user.set({"ics_token": token}, merge=True)
    return token


def chat_for_ics_token(token: str) -> str | None:
    """Owner chat of a feed token. The format is checked before any lookup."""
    if not _ICS_TOKEN.fullmatch(token):
        return None
    return (_data(_doc("ics_tokens", token).get()) or {}).get("chat_id")


def mark_ics_fetch(token: str) -> None:
    """A calendar app read the feed: proof that the subscription works.
    ponytail: one write per fetch (apps poll every 15 min to hours); skip
    writes within the hour if Firestore writes ever matter."""
    _doc("ics_tokens", token).set({"last_fetch": _now()}, merge=True)


def calendar_status(ctx: ToolContext) -> str:
    """Which calendars are connected, and whether a subscribed app has read the
    feed yet. Connection state only, no events. Sent to the user as is."""
    lang = ctx.lang
    prefs = get_preferences(ctx.chat_id)
    lines = []
    if prefs.get("gcal_token_enc") or prefs.get("gcal_id"):
        lines.append(t(lang, "cal_status_google"))
    if prefs.get("ics_url_enc"):
        lines.append(t(lang, "cal_status_import"))
    token = (get_user(ctx.chat_id) or {}).get("ics_token")
    feed = _data(_doc("ics_tokens", token).get()) if token else None
    if feed and (last := feed.get("last_fetch")):
        minutes = max(int((_now() - last).total_seconds() // 60), 0)
        lines.append(t(lang, "cal_status_feed_ok", minutes=minutes))
    elif feed:
        lines.append(t(lang, "cal_status_feed_wait"))
    return "\n".join(lines) or t(lang, "cal_status_none")


# --- owner tools -----------------------------------------------------------------

OWNER_ONLY = "Solo el owner puede hacer eso."


def invite_beta(ctx: ToolContext, name: str) -> str:
    if ctx.role != "owner":
        return OWNER_ONLY
    code = create_invite(name)
    return f"Invitación para {name}: /start {code} (un uso, válida 24 h)."


def create_invite(name: str) -> str:
    """Single-use code, valid 24 h; also the payload of a t.me deep link."""
    code = secrets.token_urlsafe(16)
    _doc("invites", code).set(
        {"nombre": name, "used": False, "expire_at": _now() + INVITE_TTL}
    )
    return code


def all_users() -> list[tuple[str, dict]]:
    return [(s.id, s.to_dict() or {}) for s in _db().collection("users").stream()]


def revoke(chat_id: str) -> bool:
    """Remove a beta from the allowlist; the owner cannot be revoked. Their
    data is erased REVOKED_PURGE_DAYS later, unless they are let in again
    before that."""
    ref = _doc("users", chat_id)
    if (_data(ref.get()) or {}).get("rol") != "beta":
        return False
    ref.delete()
    due = _now() + timedelta(days=REVOKED_PURGE_DAYS)
    _doc("purge", chat_id).set({"due": due, "expire_at": due + timedelta(days=30)})
    return True


def due_purges() -> list[str]:
    """Revoked chats whose wait is over."""
    now = _now()
    return [
        s.id
        for s in _db().collection("purge").stream()
        if (s.to_dict() or {})["due"] <= now
    ]


def cancel_purge(chat_id: str) -> None:
    _doc("purge", chat_id).delete()


def purge_user(chat_id: str) -> None:
    """Erase the chat's data and its access. The ledger CSV export keeps its
    rows under the alias, which nothing links to the chat any more."""
    reset_user(chat_id)
    for name in ("users", "requests", "purge"):
        _doc(name, chat_id).delete()


def user_alias(chat_id: str, user: dict) -> str:
    """The random id that stands for the user in the ledger CSV export."""
    if alias := user.get("alias"):
        return str(alias)
    alias = secrets.token_hex(6)
    _doc("users", chat_id).set({"alias": alias}, merge=True)
    return alias


def reset_user(chat_id: str) -> None:
    """Erase everything stored for the chat except its access (nombre, rol):
    ledger, agenda, meals, split checks, LLM history, preferences, settings and
    the feed link. The rate and spend counters stay, so a reset never lifts the
    daily LLM cap."""
    db = _db()
    user = _doc("users", chat_id)
    data = _data(user.get()) or {}
    if token := data.get("ics_token"):
        _doc("ics_tokens", token).delete()
    # the doc plus movimientos / eventos / registros / divisiones
    for name in ("ledger", "agenda", "comidas", "cuentas"):
        db.recursive_delete(db.collection(name).document(chat_id))
    for name in ("history", "preferences"):
        _doc(name, chat_id).delete()
    user.set({k: data[k] for k in ("nombre", "rol") if k in data})


def list_users(ctx: ToolContext) -> str:
    if ctx.role != "owner":
        return OWNER_ONLY
    users = [s.to_dict() or {} for s in _db().collection("users").stream()]
    return "\n".join(f"{u.get('nombre', '?')} ({u.get('rol', '?')})" for u in users)
