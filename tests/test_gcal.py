import dataclasses
import json
import logging
import re
import sys
import types
from datetime import UTC, datetime
from unittest.mock import MagicMock
from zoneinfo import ZoneInfo

import httpx
import pytest
import respx
from google.cloud import firestore

from assistant.config import WorkerSettings, get_worker_settings
from assistant.context import ToolContext
from assistant.services import gcal

CAL = "yo.secreto@gmail.com"
EVENTS = f"{gcal.API}/calendars/yo.secreto%40gmail.com/events"
PANAMA = ZoneInfo("America/Panama")
SINCE = datetime(2026, 9, 30, tzinfo=UTC)
UNTIL = datetime(2026, 10, 1, tzinfo=UTC)
EVENT = {
    "titulo": "Dentista",
    "inicio": "2026-09-30T09:00:00-05:00",
    "fin": "2026-09-30T10:00:00-05:00",
    "ubicacion": "Clínica",
    "recordatorio_min": 15,
}


def ctx(chat_id: str = "42") -> ToolContext:
    now = datetime(2026, 9, 29, 12, tzinfo=PANAMA)
    return ToolContext(chat_id, "owner", "USD", "America/Panama", 1, now)


@pytest.fixture(autouse=True)
def creds(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = types.SimpleNamespace(valid=True, token="tok")  # noqa: S106
    monkeypatch.setattr(gcal, "_creds", lambda: fake)


@pytest.fixture
def prefs(monkeypatch: pytest.MonkeyPatch) -> dict:
    """In-memory preferences/users behind the state module."""
    store: dict = {"gcal_id": CAL}
    mod = types.SimpleNamespace(
        get_preferences=lambda chat_id: store if chat_id == "42" else {},
        get_user=lambda chat_id: {"zona_horaria": "America/Panama"},
    )
    monkeypatch.setitem(sys.modules, "assistant.services.state", mod)
    return store


@pytest.fixture
def db(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    fake = MagicMock()
    monkeypatch.setattr(gcal, "_db", lambda: fake)
    return fake


def test_event_id_is_deterministic_and_valid_for_google() -> None:
    gid = gcal.event_gid("42", "100")
    assert gid == gcal.event_gid("42", "100") != gcal.event_gid("7", "100")
    assert re.fullmatch(r"[a-v0-9]{5,1024}", gid) and gcal._OURS.fullmatch(gid)


# --- Google sign-in (OAuth) ------------------------------------------------------


@pytest.fixture
def oauth(monkeypatch: pytest.MonkeyPatch) -> WorkerSettings:
    s = dataclasses.replace(
        get_worker_settings(),
        api_url="https://api.example",
        kms_key="k",
        google_client_id="cid",
        google_client_secret="csecret",  # noqa: S106 # pragma: allowlist secret
    )
    monkeypatch.setattr(gcal, "get_worker_settings", lambda: s)
    monkeypatch.setattr(gcal.crypto, "encrypt", lambda k, p, c: f"enc({p},{c})")
    monkeypatch.setattr(gcal.crypto, "decrypt", lambda k, e, c: e[4:-4])
    gcal._tokens.clear()
    return s


def test_auth_url_asks_offline_calendar_events_only(oauth: WorkerSettings) -> None:
    url = httpx.URL(gcal.auth_url(oauth, "st"))
    assert str(url).startswith(gcal.AUTH_URL)
    assert dict(url.params) == {
        "client_id": "cid",
        "redirect_uri": "https://api.example/oauth/google/callback",
        "response_type": "code",
        "scope": "https://www.googleapis.com/auth/calendar.events",
        "access_type": "offline",
        "prompt": "consent",
        "include_granted_scopes": "true",
        "state": "st",
    }


@respx.mock
def test_connect_stores_the_encrypted_refresh_token(
    oauth: WorkerSettings, db: MagicMock
) -> None:
    body = {"access_token": "at", "refresh_token": "rt", "expires_in": 3599}
    token = respx.post(gcal.TOKEN_URL).respond(200, json=body)
    gcal.connect("42", "c0de", oauth)
    sent = dict(httpx.QueryParams(token.calls[0].request.read().decode()))
    assert sent["code"] == "c0de" and sent["grant_type"] == "authorization_code"
    assert sent["redirect_uri"] == "https://api.example/oauth/google/callback"
    db.collection().document().set.assert_called_once_with(
        {
            "gcal_token_enc": "enc(rt,42)",
            "gcal_id": firestore.DELETE_FIELD,
            "ics_url_enc": firestore.DELETE_FIELD,
            "ics_url": firestore.DELETE_FIELD,
        },
        merge=True,
    )
    assert gcal._tokens["42"][2] == "at"  # the first access token is reused


@pytest.mark.parametrize(
    "response", [httpx.Response(200, json={"access_token": "at"}), httpx.Response(400)]
)
def test_connect_without_refresh_token_stores_nothing(
    oauth: WorkerSettings, db: MagicMock, response: httpx.Response
) -> None:
    with respx.mock:
        respx.post(gcal.TOKEN_URL).mock(return_value=response)
        with pytest.raises((ValueError, httpx.HTTPStatusError)):
            gcal.connect("42", "c0de", oauth)
    db.collection().document().set.assert_not_called()


@respx.mock
def test_user_token_calls_primary_and_is_cached(
    oauth: WorkerSettings, prefs: dict
) -> None:
    prefs.clear()
    prefs["gcal_token_enc"] = "enc(rt,42)"
    token = respx.post(gcal.TOKEN_URL).respond(
        200, json={"access_token": "user-at", "expires_in": 3599}
    )
    primary = f"{gcal.API}/calendars/primary/events"
    events = respx.get(primary).respond(200, json={"items": []})
    insert = respx.post(primary).respond(200, json={})
    assert gcal.busy_blocks("42", SINCE, UNTIL) == []
    gcal.mirror_create(ctx(), "100", EVENT)
    assert token.call_count == 1  # refreshed once, then cached
    assert dict(httpx.QueryParams(token.calls[0].request.read().decode())) == {
        "client_id": "cid",
        "client_secret": "csecret",  # pragma: allowlist secret
        "refresh_token": "rt",
        "grant_type": "refresh_token",
    }
    for route in (events, insert):
        assert route.calls[0].request.headers["Authorization"] == "Bearer user-at"


def test_revoked_grant_unlinks(
    oauth: WorkerSettings,
    prefs: dict,
    db: MagicMock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    prefs.clear()
    prefs["gcal_token_enc"] = "enc(rt,42)"
    with respx.mock:  # no Calendar call either
        respx.post(gcal.TOKEN_URL).respond(400, json={"error": "invalid_grant"})
        assert gcal.busy_blocks("42", SINCE, UNTIL) == []
    db.collection().document().set.assert_called_once_with(
        {"gcal_token_enc": firestore.DELETE_FIELD}, merge=True
    )
    assert "gcal_token_revoked" in caplog.text and "rt" not in caplog.text


@respx.mock
def test_disconnect_revokes_and_clears_every_calendar(
    oauth: WorkerSettings, prefs: dict, db: MagicMock
) -> None:
    prefs["gcal_token_enc"] = "enc(rt,42)"
    revoke = respx.post(gcal.REVOKE_URL).respond(200)
    gcal.disconnect("42")
    assert revoke.calls[0].request.read() == b"token=rt"
    fields = ("gcal_token_enc", "gcal_id", "ics_url_enc", "ics_url")
    db.collection().document().set.assert_called_once_with(
        {f: firestore.DELETE_FIELD for f in fields}, merge=True
    )


def test_disconnect_legacy_needs_no_revoke(prefs: dict, db: MagicMock) -> None:
    with respx.mock:  # any request would fail as unmatched
        gcal.disconnect("42")
    db.collection().document().set.assert_called_once()


# --- mirror ----------------------------------------------------------------------


@respx.mock
def test_mirror_create_inserts_with_deterministic_id(prefs: dict) -> None:
    route = respx.post(EVENTS).respond(200, json={})
    gcal.mirror_create(ctx(), "100", EVENT)
    body = route.calls[0].request.read().decode()
    assert gcal.event_gid("42", "100") in body
    sent = json.loads(body)
    assert sent["start"] == {"dateTime": EVENT["inicio"]}
    assert sent["location"] == "Clínica"
    assert sent["reminders"] == {
        "useDefault": False,
        "overrides": [{"method": "popup", "minutes": 15}],
    }


@respx.mock
def test_mirror_create_409_is_done(
    prefs: dict, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO)
    respx.post(EVENTS).respond(409)
    gcal.mirror_create(ctx(), "100", {**EVENT, "recordatorio_min": None})
    assert "gcal_mirror" in caplog.text and "failed" not in caplog.text


@pytest.mark.parametrize("code", [204, 404, 410])
def test_mirror_cancel_tolerates_gone(
    prefs: dict, caplog: pytest.LogCaptureFixture, code: int
) -> None:
    with respx.mock:
        route = respx.delete(f"{EVENTS}/{gcal.event_gid('42', '100')}")
        route.respond(code)
        gcal.mirror_cancel(ctx(), "100")
        assert route.called
    assert "failed" not in caplog.text


@pytest.mark.parametrize(
    "response", [httpx.Response(500), httpx.ConnectTimeout("t"), RuntimeError("x")]
)
def test_mirror_failures_never_raise_and_log_no_pii(
    prefs: dict, caplog: pytest.LogCaptureFixture, response: object
) -> None:
    with respx.mock:
        kw = (
            {"side_effect": response}
            if isinstance(response, Exception)
            else {"return_value": response}
        )
        respx.post(EVENTS).mock(**kw)
        respx.delete(url__regex=r".*/events/.*").mock(**kw)
        gcal.mirror_create(ctx(), "100", EVENT)
        gcal.mirror_cancel(ctx(), "100")
    assert "gcal_mirror_failed" in caplog.text and "gcal_unmirror_failed" in caplog.text
    for pii in ("secreto", "Dentista", "42"):
        assert pii not in caplog.text


def test_mirror_is_noop_when_unlinked(prefs: dict) -> None:
    with respx.mock:  # any request would fail as unmatched
        gcal.mirror_create(ctx("7"), "100", EVENT)
        gcal.mirror_cancel(ctx("7"), "100")


# --- ocupados --------------------------------------------------------------------


@respx.mock
def test_busy_blocks_exclude_our_mirrors_and_free_events(prefs: dict) -> None:
    mine = gcal.event_gid("42", "100")
    route = respx.get(EVENTS).respond(
        200,
        json={
            "items": [
                {
                    "id": mine,
                    "start": {"dateTime": "2026-09-30T09:00:00-05:00"},
                    "end": {"dateTime": "2026-09-30T10:00:00-05:00"},
                },
                {
                    "id": "abc",
                    "start": {"dateTime": "2026-09-30T11:00:00-05:00"},
                    "end": {"dateTime": "2026-09-30T12:00:00-05:00"},
                },
                {
                    "id": "free",
                    "transparency": "transparent",
                    "start": {"dateTime": "2026-09-30T13:00:00-05:00"},
                    "end": {"dateTime": "2026-09-30T14:00:00-05:00"},
                },
                {"id": "gone", "status": "cancelled"},
                {
                    "id": "allday",
                    "start": {"date": "2026-09-30"},
                    "end": {"date": "2026-10-01"},
                },
            ]
        },
    )
    assert gcal.busy_blocks("42", SINCE, UNTIL) == [
        (
            datetime(2026, 9, 30, 5, tzinfo=UTC),
            datetime(2026, 10, 1, 5, tzinfo=UTC),
            "Ocupado",
        ),
        (
            datetime(2026, 9, 30, 16, tzinfo=UTC),
            datetime(2026, 9, 30, 17, tzinfo=UTC),
            "Ocupado",
        ),
    ]
    params = route.calls[0].request.url.params
    assert params["singleEvents"] == "true"
    assert params["timeMin"] == "2026-09-30T00:00:00+00:00"


@pytest.mark.parametrize(
    "response", [httpx.Response(403), httpx.ConnectTimeout("t"), httpx.Response(200)]
)
def test_busy_blocks_failure_is_empty(
    prefs: dict, caplog: pytest.LogCaptureFixture, response: object
) -> None:
    with respx.mock:
        if isinstance(response, Exception):
            respx.get(EVENTS).mock(side_effect=response)
        else:
            respx.get(EVENTS).mock(return_value=response)
        assert gcal.busy_blocks("42", SINCE, UNTIL) == []
    assert "gcal_busy_failed" in caplog.text and "secreto" not in caplog.text


def test_legacy_shared_calendar_uses_the_service_account(prefs: dict) -> None:
    assert "gcal_token_enc" not in prefs  # only the old gcal_id
    with respx.mock:
        route = respx.get(EVENTS).respond(200, json={"items": []})
        assert gcal.busy_blocks("42", SINCE, UNTIL) == []
    assert route.calls[0].request.headers["Authorization"] == "Bearer tok"


def test_busy_blocks_unlinked_is_empty(prefs: dict) -> None:
    with respx.mock:
        assert gcal.busy_blocks("7", SINCE, UNTIL) == []


def test_credentials_are_lazy_cached_and_refreshed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.undo()  # drop the fake creds
    gcal._creds.cache_clear()
    creds = MagicMock(valid=False, token="new")  # noqa: S106
    default = MagicMock(return_value=(creds, "p"))
    monkeypatch.setattr("google.auth.default", default)
    with respx.mock:
        respx.get("https://x.example/").respond(200)
        monkeypatch.setattr(gcal, "API", "https://x.example")
        gcal._call("GET", "/")
        gcal._call("GET", "/")
    default.assert_called_once_with(scopes=[gcal.SCOPE])
    assert creds.refresh.call_count == 2
    gcal._creds.cache_clear()


def test_backfill_mirrors_only_active_items(
    db: MagicMock, prefs: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    snaps = [
        types.SimpleNamespace(id="1", to_dict=lambda: {"estado": "activo"}),
        types.SimpleNamespace(id="2", to_dict=lambda: {"estado": "cancelado"}),
    ]
    db.collection().document().collection().where().stream.return_value = snaps
    mirrored: list[str] = []
    monkeypatch.setattr(gcal, "mirror_create", lambda c, i, e: mirrored.append(i))
    assert gcal._backfill(ctx()) == 1
    assert mirrored == ["1"]


# --- changes made in Google ------------------------------------------------------


@respx.mock
def test_changes_pages_and_keeps_only_our_mirrors(prefs: dict) -> None:
    mine, other = gcal.event_gid("42", "100"), gcal.event_gid("42", "101")
    moved = {
        "id": mine,
        "summary": "Dentista",
        "start": {"dateTime": "2026-09-30T11:00:00-05:00"},
        "end": {"date": "2026-10-01"},
    }
    route = respx.get(EVENTS).mock(
        side_effect=[
            httpx.Response(200, json={"items": [moved], "nextPageToken": "p2"}),
            httpx.Response(
                200,
                json={"items": [{"id": other, "status": "cancelled"}, {"id": "abc"}]},
            ),
        ]
    )
    assert gcal.changes("42", SINCE, PANAMA) == [
        (
            mine,
            False,
            datetime(2026, 9, 30, 16, tzinfo=UTC),
            datetime(2026, 10, 1, 5, tzinfo=UTC),
            "Dentista",
        ),
        (other, True, SINCE, SINCE, ""),
    ]
    first, second = (c.request.url.params for c in route.calls)
    assert first["updatedMin"] == "2026-09-30T00:00:00+00:00"
    assert first["showDeleted"] == "true" and "pageToken" not in first
    assert second["pageToken"] == "p2"


@pytest.mark.parametrize("response", [httpx.Response(410), httpx.ConnectTimeout("t")])
def test_changes_failure_or_unlinked_is_empty(
    prefs: dict, caplog: pytest.LogCaptureFixture, response: object
) -> None:
    with respx.mock:
        if isinstance(response, Exception):
            respx.get(EVENTS).mock(side_effect=response)
        else:
            respx.get(EVENTS).mock(return_value=response)
        assert gcal.changes("42", SINCE, PANAMA) == []
        assert gcal.changes("7", SINCE, PANAMA) == []
    assert "gcal_changes_failed" in caplog.text and "secreto" not in caplog.text
