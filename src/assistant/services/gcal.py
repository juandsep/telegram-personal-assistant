"""Mirror the Firestore agenda into the user's own Google Calendar, instantly.

The user signs in with Google from Telegram (``calendario`` → Conectar → Google;
the OAuth routes live in ``api.py``) and grants ``calendar.events`` only. The
refresh token is stored encrypted with Cloud KMS in
``preferences/{chat_id}.gcal_token_enc`` and every call goes to the user's
``primary`` calendar with a short-lived access token. Users linked before
OAuth keep ``preferences/{chat_id}.gcal_id``, a calendar shared with the
service account, which is still served with the service's own ADC token.
Firestore stays the source of truth; every mirror call is best effort and never
raises into the turn. Google event ids derive from ``chat_id:evento_id`` so a
retry is idempotent (409 on insert and 404/410 on delete count as done).

Busy times come from ``events.list`` (freeBusy needs a broader scope), skipping
our own mirrored events. Tokens, calendar ids, titles and chat_ids are secrets
or PII: log status codes and error classes only.
"""

from __future__ import annotations

import hashlib
import importlib
import logging
import os
import re
import time as clock
from datetime import UTC, date, datetime, time
from functools import cache
from typing import Any
from urllib.parse import quote, urlencode
from zoneinfo import ZoneInfo

import httpx
from google.cloud import firestore
from google.cloud.firestore import FieldFilter

from assistant.config import WorkerSettings, get_worker_settings
from assistant.context import ToolContext
from assistant.services import crypto

log = logging.getLogger(__name__)
# httpx logs every request URL at INFO; the URL holds the calendar id.
logging.getLogger("httpx").setLevel(logging.WARNING)

API = "https://www.googleapis.com/calendar/v3"
SCOPE = "https://www.googleapis.com/auth/calendar.events"
AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"  # noqa: S105 # pragma: allowlist secret
REVOKE_URL = "https://oauth2.googleapis.com/revoke"
CALLBACK = "/oauth/google/callback"
TIMEOUT_S = 5.0
LABEL = "Ocupado"
DEFAULT_ZONE = "America/Panama"
_MIO = re.compile(r"bj[0-9a-f]{40}")  # ids of our mirrored events


@cache
def _db() -> firestore.Client:
    return firestore.Client(
        project=os.environ.get("GCP_PROJECT_ID") or None,
        database=os.environ.get("FIRESTORE_DATABASE") or None,  # staging has its own
    )


@cache
def _creds() -> Any:
    import google.auth

    creds, _ = google.auth.default(scopes=[SCOPE])
    return creds


# ponytail: per-instance cache of access tokens (1 h each); a cold instance
# refreshes once per chat.
_tokens: dict[str, tuple[str, float, str]] = {}  # chat_id: (enc, expiry, token)


def _call(
    method: str, path: str, token: str | None = None, **kwargs: Any
) -> httpx.Response:
    """A Calendar API call with the user's access token, or the service's own
    credentials (legacy shared calendars) when ``token`` is None."""
    if token is None:
        creds = _creds()
        if not creds.valid:
            import google.auth.transport.requests

            creds.refresh(google.auth.transport.requests.Request())
        token = creds.token
    headers = {"Authorization": f"Bearer {token}"}
    return httpx.request(
        method, f"{API}{path}", headers=headers, timeout=TIMEOUT_S, **kwargs
    )


def _events(cal: str) -> str:
    return f"/calendars/{quote(cal, safe='')}/events"


def _prefs(chat_id: str) -> Any:
    return _db().collection("preferences").document(chat_id)


def _client(s: WorkerSettings) -> dict[str, str]:
    return {"client_id": s.google_client_id, "client_secret": s.google_client_secret}


def _cache_token(chat_id: str, enc: str, body: dict) -> str:
    expiry = clock.monotonic() + int(body.get("expires_in", 3600)) - 60
    _tokens[chat_id] = (enc, expiry, str(body["access_token"]))
    return str(body["access_token"])


def _access_token(chat_id: str, enc: str) -> str:
    """A fresh access token from the stored refresh token. A revoked grant
    (400 invalid_grant) unlinks the calendar, then raises like any failure."""
    hit = _tokens.get(chat_id)
    if hit and hit[0] == enc and hit[1] > clock.monotonic():
        return hit[2]
    s = get_worker_settings()
    data = {
        **_client(s),
        "refresh_token": crypto.decrypt(s.kms_key, enc, chat_id),
        "grant_type": "refresh_token",
    }
    resp = httpx.post(TOKEN_URL, data=data, timeout=TIMEOUT_S)
    if resp.status_code == 400 and "invalid_grant" in resp.text:
        _prefs(chat_id).set({"gcal_token_enc": firestore.DELETE_FIELD}, merge=True)
        _tokens.pop(chat_id, None)
        log.warning("gcal_token_revoked")
    resp.raise_for_status()
    return _cache_token(chat_id, enc, resp.json())


def _linked(chat_id: str) -> tuple[str, str | None] | None:
    """(calendar id, access token) of the chat's calendar: ``primary`` with the
    user's token, or a legacy shared ``gcal_id`` with None; None if unlinked."""
    state = importlib.import_module("assistant.services.state")
    prefs = state.get_preferences(chat_id)
    if enc := prefs.get("gcal_token_enc"):
        return "primary", _access_token(chat_id, enc)
    if cal := prefs.get("gcal_id"):
        return cal, None
    return None


def evento_gid(chat_id: str, evento_id: str) -> str:
    """Google event id: base32hex (0-9a-v), so hex digits are valid as is."""
    return "bj" + hashlib.sha256(f"{chat_id}:{evento_id}".encode()).hexdigest()[:40]


def auth_url(s: WorkerSettings, state_token: str) -> str:
    """Google's consent page; it comes back to ``CALLBACK`` with a code."""
    query = {
        "client_id": s.google_client_id,
        "redirect_uri": f"{s.api_url}{CALLBACK}",
        "response_type": "code",
        "scope": SCOPE,
        "access_type": "offline",
        "prompt": "consent",
        "include_granted_scopes": "true",
        "state": state_token,
    }
    return f"{AUTH_URL}?{urlencode(query)}"


def conectar(chat_id: str, code: str, s: WorkerSettings) -> None:
    """Swap the sign-in code for tokens and keep the refresh token, encrypted.
    The chat's only calendar: an iCal link or a legacy shared id is dropped."""
    data = {
        **_client(s),
        "code": code,
        "redirect_uri": f"{s.api_url}{CALLBACK}",
        "grant_type": "authorization_code",
    }
    resp = httpx.post(TOKEN_URL, data=data, timeout=TIMEOUT_S)
    resp.raise_for_status()
    body = resp.json()
    if not body.get("refresh_token"):
        raise ValueError("no_refresh_token")
    enc = crypto.encrypt(s.kms_key, body["refresh_token"], chat_id)
    _prefs(chat_id).set(
        {
            "gcal_token_enc": enc,
            "gcal_id": firestore.DELETE_FIELD,
            "ics_url_enc": firestore.DELETE_FIELD,
            "ics_url": firestore.DELETE_FIELD,
        },
        merge=True,
    )
    _cache_token(chat_id, enc, body)
    log.info("gcal_link")


def desconectar(chat_id: str) -> None:
    """Forget the chat's calendar; revoke the Google grant best effort."""
    state = importlib.import_module("assistant.services.state")
    enc = state.get_preferences(chat_id).get("gcal_token_enc")
    _tokens.pop(chat_id, None)
    if enc:
        try:
            token = crypto.decrypt(get_worker_settings().kms_key, enc, chat_id)
            httpx.post(REVOKE_URL, data={"token": token}, timeout=TIMEOUT_S)
        except Exception as exc:
            log.warning("gcal_revoke_failed code=%s", type(exc).__name__)
    fields = ("gcal_token_enc", "gcal_id", "ics_url_enc", "ics_url")
    _prefs(chat_id).set({f: firestore.DELETE_FIELD for f in fields}, merge=True)
    log.info("gcal_unlink")


def _backfill(ctx: ToolContext) -> int:
    """Mirror the upcoming active items created before linking; the ids are
    deterministic, so linking again only gets 409s."""
    futuros = (
        _db()
        .collection("agenda")
        .document(ctx.chat_id)
        .collection("eventos")
        .where(filter=FieldFilter("fin_utc", ">", ctx.ahora.astimezone(UTC)))
    )
    n = 0
    for snap in futuros.stream():
        evento = snap.to_dict() or {}
        if evento.get("estado") == "activo":
            espejo_crear(ctx, snap.id, evento)
            n += 1
    return n


def _best_effort(
    op: str, chat_id: str, method: str, sub: str, ok: tuple[int, ...], **kw: Any
) -> None:
    """Call the linked calendar; 2xx and the ``ok`` idempotent codes are done."""
    try:
        linked = _linked(chat_id)
        if not linked:
            return
        cal, token = linked
        code = _call(method, f"{_events(cal)}{sub}", token, **kw).status_code
        if code < 300 or code in ok:
            log.info("gcal_%s", op)
        else:
            log.error("gcal_%s_failed code=%s", op, code)
    except Exception as exc:  # never raise into the turn
        log.error("gcal_%s_failed code=%s", op, type(exc).__name__)


def espejo_crear(ctx: ToolContext, evento_id: str, evento: dict) -> None:
    body: dict[str, Any] = {
        "id": evento_gid(ctx.chat_id, evento_id),
        "summary": evento["titulo"],
        "start": {"dateTime": evento["inicio"]},
        "end": {"dateTime": evento["fin"]},
    }
    if evento.get("ubicacion"):
        body["location"] = evento["ubicacion"]
    if evento.get("recordatorio_min") is not None:
        popup = {"method": "popup", "minutes": evento["recordatorio_min"]}
        body["reminders"] = {"useDefault": False, "overrides": [popup]}
    _best_effort("mirror", ctx.chat_id, "POST", "", (409,), json=body)


def espejo_cancelar(ctx: ToolContext, evento_id: str) -> None:
    sub = f"/{evento_gid(ctx.chat_id, evento_id)}"
    _best_effort("unmirror", ctx.chat_id, "DELETE", sub, (404, 410))


def _as_dt(value: dict, zone: ZoneInfo) -> datetime:
    if "dateTime" in value:
        return datetime.fromisoformat(value["dateTime"]).astimezone(UTC)
    dia = date.fromisoformat(value["date"])  # all-day: midnight in the user's zone
    return datetime.combine(dia, time(), zone).astimezone(UTC)


def ocupados(
    chat_id: str, desde: datetime, hasta: datetime
) -> list[tuple[datetime, datetime, str]]:
    """Busy blocks of the linked calendar minus our mirrors, UTC; [] on failure."""
    try:
        linked = _linked(chat_id)
        if not linked:
            return []
        cal, token = linked
        params = {
            "timeMin": desde.astimezone(UTC).isoformat(),
            "timeMax": hasta.astimezone(UTC).isoformat(),
            "singleEvents": "true",
            "maxResults": 250,
            "fields": "items(id,status,transparency,start,end)",
        }
        resp = _call("GET", _events(cal), token, params=params)
        if resp.status_code != 200:
            log.error("gcal_busy_failed code=%s", resp.status_code)
            return []
        user = importlib.import_module("assistant.services.state").get_user(chat_id)
        zone = ZoneInfo((user or {}).get("zona_horaria") or DEFAULT_ZONE)
        return sorted(
            (_as_dt(ev["start"], zone), _as_dt(ev["end"], zone), LABEL)
            for ev in resp.json().get("items", [])
            if not _MIO.fullmatch(ev.get("id", ""))
            and ev.get("status") != "cancelled"
            and ev.get("transparency") != "transparent"
        )
    except Exception as exc:  # never raise into the conversation
        log.error("gcal_busy_failed code=%s", type(exc).__name__)
    return []
