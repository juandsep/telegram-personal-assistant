import base64
import dataclasses
import json
import time
from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import MagicMock
from urllib.parse import urlencode

import httpx
import pytest
import respx
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi.testclient import TestClient
from firestore_fake import FakeDB

from assistant import api
from assistant.app import app
from assistant.config import get_worker_settings
from assistant.i18n import t
from assistant.services import agenda, fx, gcal, ledger, pubsub, state

URL = "/tg/test-path"
HEADERS = {"X-Telegram-Bot-Api-Secret-Token": "test-secret"}  # pragma: allowlist secret


def update(text="hola", update_id=1, chat_id=42):
    return {"update_id": update_id, "message": {"chat": {"id": chat_id}, "text": text}}


@pytest.fixture
def fake(monkeypatch):
    users = {"42": {"rol": "owner"}}
    seen: set[int] = set()

    def mark(update_id):
        new = update_id not in seen
        seen.add(update_id)
        return new

    def redeem(code, chat_id):
        if code != "good":
            return False
        users[chat_id] = {"rol": "beta"}
        return True

    m = MagicMock()
    monkeypatch.setattr(state, "get_user", users.get)
    monkeypatch.setattr(state, "mark_processed", mark)
    monkeypatch.setattr(state, "unmark_processed", lambda uid: seen.discard(uid))
    monkeypatch.setattr(state, "redeem_invite", MagicMock(side_effect=redeem))
    monkeypatch.setattr(pubsub, "publish", m.publish)
    return m


client = TestClient(app)


def test_missing_header_403(fake) -> None:
    assert client.post(URL, json=update()).status_code == 403
    fake.publish.assert_not_called()


def test_wrong_path_403(fake) -> None:
    assert client.post("/tg/wrong", json=update(), headers=HEADERS).status_code == 403


def test_known_chat_published(fake) -> None:
    body = update()
    resp = client.post(URL, json=body, headers=HEADERS)
    assert resp.status_code == 200
    assert resp.json() == {
        "method": "sendChatAction",
        "chat_id": "42",
        "action": "typing",
    }
    fake.publish.assert_called_once_with("assistant-updates", body)


def test_callback_query_published(fake) -> None:
    body = {
        "update_id": 5,
        "callback_query": {"id": "q", "data": "ok:t", "message": {"chat": {"id": 42}}},
    }
    assert client.post(URL, json=body, headers=HEADERS).status_code == 200
    fake.publish.assert_called_once()


def test_unknown_chat_dropped(fake) -> None:
    body = update(chat_id=99)
    assert client.post(URL, json=body, headers=HEADERS).status_code == 200
    fake.publish.assert_not_called()
    state.redeem_invite.assert_not_called()


def test_repeated_update_not_republished(fake) -> None:
    for _ in range(2):
        assert client.post(URL, json=update(), headers=HEADERS).status_code == 200
    assert fake.publish.call_count == 1


def test_start_with_valid_invite(fake) -> None:
    body = update("/start good", chat_id=99)
    assert client.post(URL, json=body, headers=HEADERS).status_code == 200
    fake.publish.assert_called_once()


def test_start_with_invalid_invite_is_noop(fake) -> None:
    body = update("/start bad", chat_id=99)
    assert client.post(URL, json=body, headers=HEADERS).status_code == 200
    fake.publish.assert_not_called()


def test_garbage_and_unsupported_updates_acked(fake) -> None:
    assert client.post(URL, content=b"{", headers=HEADERS).status_code == 200
    body = {"update_id": 3, "edited_message": {}}
    assert client.post(URL, json=body, headers=HEADERS).status_code == 200
    fake.publish.assert_not_called()


def test_publish_failure_lets_telegram_retry(fake) -> None:
    fake.publish.side_effect = RuntimeError("down")
    assert client.post(URL, json=update(), headers=HEADERS).status_code == 500
    fake.publish.side_effect = None
    assert client.post(URL, json=update(), headers=HEADERS).status_code == 200
    assert fake.publish.call_count == 2


# --- ICS feed --------------------------------------------------------------------


@pytest.fixture
def ics_db(monkeypatch):
    """state._db with one feed token; agenda items for chat 42."""
    db = MagicMock()
    tokens = {"t" * 32: {"chat_id": "42"}}

    def document(token):
        data = tokens.get(token)
        snap = MagicMock(exists=data is not None)
        snap.to_dict.return_value = data
        return MagicMock(get=MagicMock(return_value=snap))

    db.collection.return_value.document.side_effect = document
    monkeypatch.setattr(state, "_db", lambda: db)
    items = MagicMock(
        return_value=[
            {
                "id": "100",
                "titulo": "Cena, vino; y más",
                "ubicacion": "",
                "inicio_utc": datetime(2026, 10, 1, 1, tzinfo=UTC),
                "fin_utc": datetime(2026, 10, 1, 2, tzinfo=UTC),
                "recordatorio_min": 15,
            }
        ]
    )
    monkeypatch.setattr(agenda, "_items", items)
    return db


@pytest.mark.parametrize(
    "path", ["/ics/short.ics", f"/ics/{'a' * 31}%2F.ics", f"/ics/{'a' * 33}.ics"]
)
def test_ics_bad_token_404_without_lookup(ics_db, path) -> None:
    assert client.get(path).status_code == 404
    ics_db.collection.assert_not_called()


def test_ics_unknown_token_404(ics_db) -> None:
    assert client.get(f"/ics/{'u' * 32}.ics").status_code == 404
    ics_db.collection.assert_called_with("ics_tokens")


def test_ics_feed(ics_db, caplog, monkeypatch) -> None:
    mark = MagicMock()
    monkeypatch.setattr(state, "mark_ics_fetch", mark)
    caplog.set_level("INFO")
    resp = client.get(f"/ics/{'t' * 32}.ics")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "text/calendar; charset=utf-8"
    assert resp.headers["cache-control"] == "private, max-age=300"
    body = resp.text
    assert body.startswith("BEGIN:VCALENDAR\r\n") and body.endswith("END:VCALENDAR\r\n")
    assert "SUMMARY:Cena\\, vino\\; y más\r\n" in body
    assert "UID:100@botjonh\r\n" in body and "DTSTART:20261001T010000Z\r\n" in body
    assert "BEGIN:VALARM\r\n" in body and "TRIGGER:-PT15M\r\n" in body
    assert agenda._items.call_args.args[0] == "42"
    ours = [r.getMessage() for r in caplog.records if r.name.startswith("assistant")]
    assert ours == ["ics status=200"]  # the token never reaches our logs
    mark.assert_called_once_with("t" * 32)


def test_ics_subscribe_redirects_to_webcal(ics_db) -> None:
    resp = client.get(f"/ics/{'t' * 32}/suscribir", follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers["location"] == f"webcal://testserver/ics/{'t' * 32}.ics"
    assert client.get(f"/ics/{'u' * 32}/suscribir").status_code == 404
    ics_db.collection.reset_mock()
    assert client.get("/ics/short/suscribir").status_code == 404
    ics_db.collection.assert_not_called()


# --- Google sign-in --------------------------------------------------------------

STATE = "s" * 22


@pytest.fixture
def oauth(monkeypatch):
    s = dataclasses.replace(
        get_worker_settings(),
        api_url="https://api.example",
        kms_key="k",
        google_client_id="cid",
        google_client_secret="csecret",  # pragma: allowlist secret
    )
    monkeypatch.setattr(api, "get_worker_settings", lambda: s)
    states = {STATE: "42"}
    monkeypatch.setattr(state, "consume_oauth_state", lambda tok: states.pop(tok, None))
    monkeypatch.setattr(state, "get_user", {"42": {"idioma": "en", "rol": "beta"}}.get)
    db = MagicMock()
    monkeypatch.setattr(gcal, "_db", lambda: db)
    monkeypatch.setattr(gcal.crypto, "encrypt", lambda k, p, c: f"enc({p})")
    monkeypatch.setattr(gcal, "_backfill", MagicMock(return_value=2))
    return db


def test_oauth_start_redirects_to_google(oauth) -> None:
    resp = client.get(f"/oauth/google?s={STATE}", follow_redirects=False)
    assert resp.status_code == 302
    url = httpx.URL(resp.headers["location"])
    assert str(url).startswith(gcal.AUTH_URL)
    assert url.params["state"] == STATE and url.params["access_type"] == "offline"
    assert url.params["redirect_uri"] == "https://api.example/oauth/google/callback"
    assert client.get("/oauth/google?s=bad/state").status_code == 404


def test_oauth_start_refused_without_client(monkeypatch) -> None:
    unset = dataclasses.replace(get_worker_settings(), google_client_id="")
    monkeypatch.setattr(api, "get_worker_settings", lambda: unset)
    assert client.get(f"/oauth/google?s={STATE}").status_code == 404


def test_oauth_callback_links_and_notifies(oauth, caplog) -> None:
    caplog.set_level("INFO")
    with respx.mock:
        respx.post(gcal.TOKEN_URL).respond(
            200, json={"access_token": "at", "refresh_token": "rt", "expires_in": 3599}
        )
        sent = respx.post(url__regex=r".*/sendMessage").respond(200, json={"ok": True})
        resp = client.get(f"/oauth/google/callback?code=c0de&state={STATE}")
    assert resp.status_code == 200 and "Done, go back to Telegram" in resp.text
    assert resp.headers["cache-control"] == "no-store"
    assert json.loads(sent.calls[0].request.read()) == {
        "chat_id": "42",
        "text": t("en", "gcal_linked", n=2),
    }
    stored = oauth.collection().document().set.call_args.args[0]
    assert stored["gcal_token_enc"] == "enc(rt)"
    assert gcal._backfill.call_args.args[0].chat_id == "42"
    for secret in ("c0de", STATE, "rt", "42"):
        assert secret not in caplog.text
    # single use: the same link again fails without calling Google
    with respx.mock:
        again = client.get(f"/oauth/google/callback?code=c0de&state={STATE}")
    assert again.status_code == 400 and "No se pudo conectar" in again.text


@pytest.mark.parametrize(
    "query", [f"error=access_denied&state={STATE}", "code=c&state=x", "code=c"]
)
def test_oauth_callback_denied_or_bad_state(oauth, query) -> None:
    with respx.mock:  # any request would fail as unmatched
        resp = client.get(f"/oauth/google/callback?{query}")
    assert resp.status_code == 400
    oauth.collection().document().set.assert_not_called()


def test_oauth_callback_token_failure(oauth, caplog) -> None:
    with respx.mock:
        respx.post(gcal.TOKEN_URL).respond(400, json={"error": "invalid_grant"})
        resp = client.get(f"/oauth/google/callback?code=c0de&state={STATE}")
    assert resp.status_code == 502 and "Couldn't connect" in resp.text
    assert "oauth_callback status=failed error=HTTPStatusError" in caplog.text
    oauth.collection().document().set.assert_not_called()


def test_caption_only_gif_from_known_chat_published(fake) -> None:
    body = {
        "update_id": 5,
        "message": {
            "chat": {"id": 42},
            "caption": "gasto",
            "animation": {"file_id": "g"},
        },
    }
    assert client.post(URL, json=body, headers=HEADERS).status_code == 200
    fake.publish.assert_called_once_with("assistant-updates", body)


# --- web dashboard ---------------------------------------------------------------


# Stored field names: entry_kind -> tipo_mov, row_kind -> tipo, and so on.
_FIELDS = {"category": "categoria", "note": "nota", "source": "fuente"}


def _mov(day, amount, entry_kind="gasto", row_kind="registro", **extra):
    return {
        "fecha": day,
        "monto": amount,
        "tipo_mov": entry_kind,
        "tipo": row_kind,
        "creado": datetime(2026, 9, 29, tzinfo=UTC),
        **{_FIELDS.get(k, k): v for k, v in extra.items()},
    }


@pytest.fixture
def dash_db(monkeypatch):
    """Chat 42's ledger: live rows, a reversed row, an undone old-style batch."""
    db = FakeDB()
    base = "ledger/42/movimientos"
    db.store = {
        f"{base}/100-0": _mov("2026-09-03", "10.50", category="<b>x</b>", note=""),
        f"{base}/100-1": _mov(
            "2026-09-03", "4.25", category="transporte", note="uber & co"
        ),
        f"{base}/101-i0": _mov("2026-09-01", "1000.00", "ingreso", source="salario"),
        f"{base}/102-0": _mov("2026-09-10", "500.00", category="viaje"),
        f"{base}/102-0-x": _mov(
            "2026-09-10",
            "-500.00",
            category="viaje",
            row_kind="reverso",
            reversa="102-0",
        ),
        f"{base}/103-0": _mov("2026-09-12", "7.00", category="ocio", batch_id="g103"),
        f"{base}/g103-r0": _mov(
            "2026-09-12", "-7.00", category="ocio", batch_id="g103", row_kind="reverso"
        ),
        f"{base}/104-0": _mov("2026-10-01", "99.00", category="ropa"),
    }
    monkeypatch.setattr(ledger, "_db", lambda: db)
    monkeypatch.setattr(state, "get_user", {"42": {}}.get)
    key = Ed25519PrivateKey.generate()
    monkeypatch.setattr(api, "TG_PUBLIC_KEY", key.public_key())
    settings = dataclasses.replace(api.get_api_settings(), telegram_bot_id="123")
    monkeypatch.setattr(api, "get_api_settings", lambda: settings)
    return key


def init_data(key, user_id=42, auth_date=None, bot_id="123"):
    """initData as Telegram signs it for third parties (Ed25519, base64url)."""
    fields = {
        "auth_date": str(auth_date or int(time.time())),
        "query_id": "q1",
        "user": json.dumps({"id": user_id, "first_name": "Ana"}),
    }
    check = f"{bot_id}:WebAppData\n" + "\n".join(
        f"{k}={v}" for k, v in sorted(fields.items())
    )
    signature = base64.urlsafe_b64encode(key.sign(check.encode())).rstrip(b"=")
    return urlencode({**fields, "hash": "h", "signature": signature.decode()})


def data(key, month="", tz=None, **kw):
    headers = {"Authorization": "tma " + init_data(key, **kw)}
    if tz is not None:
        headers["X-Tz"] = tz
    return client.post(
        "/visor/datos" + (f"?mes={month}" if month else ""), headers=headers
    )


def test_viewer_shell() -> None:
    resp = client.get("/visor")
    assert resp.status_code == 200
    assert "telegram-web-app.js" in resp.text and "tg.initData" in resp.text
    csp = resp.headers["content-security-policy"]
    assert f"'sha256-{api._JS_HASH}'" in csp and "connect-src 'self'" in csp
    assert resp.headers["cache-control"] == "no-store"


def test_viewer_rejects_bad_init_data(dash_db) -> None:
    other = Ed25519PrivateKey.generate()
    for resp in (
        client.post("/visor/datos"),  # no header
        data(other),  # not Telegram's signature
        data(dash_db, bot_id="999"),  # signed for another bot
        data(dash_db, auth_date=int(time.time()) - 2 * 86400),  # stale
        data(dash_db, user_id=7),  # signed, but not a user
    ):
        assert resp.status_code == 403
        assert resp.headers["cache-control"] == "no-store"
    tampered = init_data(dash_db).replace("%22id%22%3A+42", "%22id%22%3A+43")
    assert "43" in tampered
    resp = client.post("/visor/datos", headers={"Authorization": "tma " + tampered})
    assert resp.status_code == 403
    assert api.init_data_chat("garbage=%", "123", time.time()) is None


def test_viewer_renders_month(dash_db, caplog) -> None:
    caplog.set_level("INFO")
    resp = data(dash_db, "2026-09")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "text/html; charset=utf-8"
    assert resp.headers["cache-control"] == "no-store"
    assert resp.headers["referrer-policy"] == "no-referrer"
    assert resp.headers["x-robots-tag"] == "noindex"
    body = resp.text
    assert "septiembre 2026" in body
    assert '<b class="in">1,000.00</b>' in body
    assert '<b class="out">14.75</b>' in body  # reversed rows and batch excluded
    assert "<b>985.25</b>" in body and "98.53%" in body
    assert "Meta 20%: 200.00 USD" in body
    assert "&lt;b&gt;x&lt;/b&gt;" in body and "<b>x</b>" not in body
    assert "Uber &amp; co" in body
    assert "500.00" not in body and "7.00" not in body and "99.00" not in body
    assert body.count("<li>") == 3
    assert 'href="?mes=2026-08"' in body and 'href="?mes=2026-10"' in body
    ours = [r.getMessage() for r in caplog.records if r.name.startswith("assistant")]
    assert ours == ["visor status=200"]


def test_viewer_in_user_language(dash_db, monkeypatch) -> None:
    monkeypatch.setattr(state, "get_user", {"42": {"idioma": "zh"}}.get)
    body = data(dash_db, "2026-09").text
    assert '<html lang="zh">' in body and "9月 2026 账单" in body
    assert "按类别支出" in body and "Gastos" not in body
    assert "交通" in body  # the stored "transporte" key, in Chinese


def test_viewer_other_months(dash_db) -> None:
    body = data(dash_db, "2026-10").text
    assert '<b class="out">99.00</b>' in body and "Sin ingresos este mes" in body
    assert "Sin movimientos." in data(dash_db, "2025-12").text
    assert data(dash_db).status_code == 200  # current month in the user's zone
    for bad in ("2026-13", "2026-9", "26-09", "2026-09-01", "x"):
        resp = data(dash_db, bad)
        assert resp.status_code == 400
        assert resp.headers["x-robots-tag"] == "noindex"


def test_viewer_in_user_currency(dash_db, monkeypatch) -> None:
    monkeypatch.setattr(state, "get_user", {"42": {"moneda": "COP"}}.get)
    monkeypatch.setattr(fx, "rate", lambda cur, day: (Decimal("4000"), "trm"))
    body = data(dash_db, "2026-09").text
    assert "Montos en COP." in body and "Montos en USD." not in body
    assert '<b class="in">4,000,000.00</b>' in body
    assert '<b class="out">59,000.00</b>' in body
    assert "Meta 20%: 800,000.00 COP" in body and "98.53%" in body


def test_viewer_takes_the_phone_time_zone(dash_db, monkeypatch, caplog) -> None:
    caplog.set_level("INFO")
    set_timezone = MagicMock()
    monkeypatch.setattr(state, "set_timezone", set_timezone)
    users = {"42": {"zona_horaria": "America/Panama"}}
    monkeypatch.setattr(state, "get_user", users.get)
    for bad in ("", "UTC", "Mars/Olympus", "../../etc/passwd", "A/" + "b" * 70):
        assert data(dash_db, tz=bad).status_code == 200
    assert data(dash_db, tz="America/Panama").status_code == 200  # unchanged
    set_timezone.assert_not_called()
    assert data(dash_db, tz="Asia/Shanghai").status_code == 200
    set_timezone.assert_called_once_with("42", "Asia/Shanghai")
    assert "zona_auto" in caplog.text and "Shanghai" not in caplog.text
    set_timezone.side_effect = RuntimeError("firestore down")  # best effort
    assert data(dash_db, tz="Europe/Madrid").status_code == 200
    assert "X-Tz" in api.VIEWER_JS


# --- reaction catalog (owner Mini App) -------------------------------------------


@pytest.fixture
def catalog(monkeypatch, dash_db) -> MagicMock:
    monkeypatch.setattr(
        state, "get_user", {"42": {"rol": "owner"}, "7": {"rol": "beta"}}.get
    )
    fake = MagicMock()
    fake.catalog.return_value = [
        {
            "id": "a" * 32,
            "etiqueta": "comida/sana",
            "url": "https://storage.googleapis.com/b/media/a.jpg",
        }
    ]
    for name in ("catalog", "add", "remove"):
        monkeypatch.setattr(api.media, name, getattr(fake, name))
    return fake


def owner(key, user_id=42) -> dict[str, str]:
    return {"Authorization": "tma " + init_data(key, user_id=user_id)}


def test_catalog_shell_and_page(dash_db, catalog) -> None:
    resp = client.get("/catalogo")
    assert resp.status_code == 200 and "tg.initData" in resp.text
    csp = resp.headers["content-security-policy"]
    assert f"'sha256-{api._CATALOG_HASH}'" in csp
    assert "img-src https://storage.googleapis.com" in csp
    page = client.post("/catalogo/datos", headers=owner(dash_db))
    assert page.status_code == 200
    assert "<h2>comida/sana (1)</h2>" in page.text
    assert f'data-id="{"a" * 32}"' in page.text
    assert '<option value="gasto/restaurantes">' in page.text  # a category tag
    assert '<option value="comida/chatarra">' in page.text


def test_catalog_is_owner_only(dash_db, catalog) -> None:
    for headers in ({}, owner(dash_db, user_id=7), owner(dash_db, user_id=99)):
        assert client.post("/catalogo/datos", headers=headers).status_code == 403
        up = client.post("/catalogo/subir?etiqueta=gasto/x", headers=headers)
        assert up.status_code == 403
        assert client.post("/catalogo/borrar?id=x", headers=headers).status_code == 403
    catalog.add.assert_not_called()
    catalog.remove.assert_not_called()


def test_catalog_upload_and_delete(dash_db, catalog) -> None:
    url = "/catalogo/subir?etiqueta=comida/sana"
    resp = client.post(url, headers=owner(dash_db), content=b"\xff\xd8\xffjpg")
    assert resp.status_code == 204
    catalog.add.assert_called_once_with("comida/sana", b"\xff\xd8\xffjpg")
    catalog.add.side_effect = api.media.MediaRejected("bad")
    assert client.post(url, headers=owner(dash_db), content=b"<svg>").status_code == 400
    big = {**owner(dash_db), "Content-Length": str(api.media.MAX_BYTES + 1)}
    assert client.post(url, headers=big, content=b"x").status_code == 413
    catalog.remove.return_value = True
    assert (
        client.post("/catalogo/borrar?id=a", headers=owner(dash_db)).status_code == 204
    )
    catalog.remove.return_value = False
    assert (
        client.post("/catalogo/borrar?id=a", headers=owner(dash_db)).status_code == 404
    )


def test_stranger_start_asks_the_owner(fake, monkeypatch) -> None:
    tg = MagicMock()
    monkeypatch.setattr(api, "Telegram", lambda token: tg)
    monkeypatch.setattr(state, "request_access", MagicMock(return_value="sent"))
    monkeypatch.setattr(state, "owner_chat_id", lambda: "42")
    body = update("/start", chat_id=99)
    body["message"]["from"] = {"first_name": "Ana", "username": "ana_m"}
    assert client.post(URL, json=body, headers=HEADERS).status_code == 200
    fake.publish.assert_not_called()
    state.request_access.assert_called_once_with("99", "Ana @ana_m", "en")
    (to_user, _), (to_owner, owner_text, buttons) = [
        c.args for c in tg.send_message.call_args_list
    ]
    assert (to_user, to_owner) == ("99", "42")
    assert "Ana @ana_m" in owner_text
    assert buttons == [[("✅ Aceptar", "ap:99"), ("❌ Rechazar", "rj:99")]]


def test_stranger_pending_request_is_quiet(fake, monkeypatch) -> None:
    tg = MagicMock()
    monkeypatch.setattr(api, "Telegram", lambda token: tg)
    monkeypatch.setattr(state, "request_access", MagicMock(return_value="pending"))
    client.post(URL, json=update("/start", chat_id=99), headers=HEADERS)
    tg.send_message.assert_not_called()
