import base64
import dataclasses
import importlib
import json
import sys
import types
from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import MagicMock
from zoneinfo import ZoneInfo

import httpx
import pytest
import respx
from fastapi.testclient import TestClient

from assistant import worker
from assistant.app import app
from assistant.authz import require_google_oidc
from assistant.channels.telegram import API_BASE, Telegram
from assistant.config import get_worker_settings
from assistant.i18n import t
from assistant.services import agenda, state

TG = f"{API_BASE}/bot123:test"
client = TestClient(app)


@pytest.fixture(autouse=True)
def google_caller(monkeypatch):
    """These tests play Pub/Sub and Cloud Tasks; test_authz covers the gate."""
    monkeypatch.setitem(app.dependency_overrides, require_google_oidc, lambda: None)


def envelope(payload) -> dict:
    data = base64.b64encode(json.dumps(payload).encode()).decode()
    return {"message": {"data": data, "messageId": "1"}, "subscription": "s"}


def message(text="¿cuánto gasté hoy?") -> dict:
    return {"update_id": 9, "message": {"chat": {"id": 42}, "text": text}}


def callback(data: str) -> dict:
    cq = {"id": "q1", "data": data, "message": {"chat": {"id": 42}}}
    return {"update_id": 10, "callback_query": cq}


def fake_module(monkeypatch, name: str, **attrs) -> types.ModuleType:
    mod = types.ModuleType(name)
    mod.__dict__.update(attrs)
    monkeypatch.setitem(sys.modules, name, mod)
    parent, _, child = name.rpartition(".")
    monkeypatch.setattr(importlib.import_module(parent), child, mod, raising=False)
    return mod


class LLMUnavailable(Exception):
    pass


@pytest.fixture
def st(monkeypatch):
    m = MagicMock()
    m.get_user.return_value = {
        "rol": "owner",
        "moneda": "USD",
        "zona_horaria": "America/Panama",
    }
    m.check_rate.return_value = True
    m.llm_spend_today.return_value = Decimal("0")
    m.get_history.return_value = []
    m.create_pending.return_value = "t" * 22
    m.get_preferences.return_value = {}
    for name in (
        "get_user",
        "check_rate",
        "llm_spend_today",
        "get_history",
        "add_llm_spend",
        "append_history",
        "pop_pending",
        "create_pending",
        "get_preferences",
        "mark_seen",
    ):
        monkeypatch.setattr(state, name, getattr(m, name))
    return m


@pytest.fixture(autouse=True)
def pick(monkeypatch):
    """The reaction catalog: empty unless a test sets a return value."""
    media = importlib.import_module("assistant.services.media")
    fake = MagicMock(return_value=None)
    monkeypatch.setattr(media, "pick", fake)
    return fake


GIF = ("https://storage.googleapis.com/b/media/g.gif", "gif")


@pytest.fixture
def llm(monkeypatch):
    result = types.SimpleNamespace(
        reply="Anotado.",
        keyboard=[[("Sí", "ok:t")]],
        messages=[{"role": "user", "content": "x"}],
        tools=[],
        cost_usd=Decimal("0.001"),
    )
    run_turn = MagicMock(return_value=result)
    fake_module(
        monkeypatch,
        "assistant.llm.client",
        run_turn=run_turn,
        LLMUnavailable=LLMUnavailable,
    )
    record = MagicMock()
    fake_module(monkeypatch, "assistant.observability.trace", record_turn=record)
    return types.SimpleNamespace(run_turn=run_turn, record=record, result=result)


@pytest.fixture
def tg():
    with respx.mock(assert_all_called=False) as router:
        router.post(f"{TG}/sendMessage").mock(
            return_value=httpx.Response(
                200, json={"ok": True, "result": {"message_id": 1}}
            )
        )
        router.post(f"{TG}/answerCallbackQuery").mock(
            return_value=httpx.Response(200, json={"ok": True})
        )
        for method in ("sendAnimation", "sendPhoto"):
            router.post(f"{TG}/{method}").mock(
                return_value=httpx.Response(200, json={"ok": True})
            )
        router.post(f"{TG}/deleteMessage").mock(
            return_value=httpx.Response(200, json={"ok": True})
        )
        for method in ("pinChatMessage", "setChatMenuButton", "unpinAllChatMessages"):
            router.post(f"{TG}/{method}").mock(
                return_value=httpx.Response(200, json={"ok": True})
            )
        yield router


def sent_texts(tg) -> list[str]:
    return [
        json.loads(c.request.read())["text"]
        for c in tg.calls
        if c.request.url.path.endswith("sendMessage")
    ]


def test_malformed_envelope_acked() -> None:
    assert client.post("/push", content=b"nope").status_code == 204
    assert client.post("/push", json={"message": {}}).status_code == 204
    bad = {"message": {"data": "!!!"}}
    assert client.post("/push", json=bad).status_code == 204
    assert client.post("/push", json=envelope({"x": 1})).status_code == 204


def test_job_routed(monkeypatch) -> None:
    run_job = MagicMock()
    monkeypatch.setitem(
        sys.modules, "assistant.jobs", types.SimpleNamespace(run_job=run_job)
    )
    assert client.post("/push", json=envelope({"job": "digest"})).status_code == 204
    run_job.assert_called_once_with("digest")


def test_warm_pings_the_api_without_running_jobs(monkeypatch) -> None:
    run_job = MagicMock()
    monkeypatch.setitem(
        sys.modules, "assistant.jobs", types.SimpleNamespace(run_job=run_job)
    )
    s = dataclasses.replace(get_worker_settings(), api_url="https://api.example")
    monkeypatch.setattr(worker, "get_worker_settings", lambda: s)
    get = MagicMock(side_effect=httpx.ConnectError("down"))
    monkeypatch.setattr(worker.httpx, "get", get)
    assert client.post("/push", json=envelope({"job": "warm"})).status_code == 204
    get.assert_called_once_with("https://api.example/health", timeout=15)
    run_job.assert_not_called()


def test_turn_in_order(st, llm, tg) -> None:
    assert client.post("/push", json=envelope(message())).status_code == 204
    ctx, text, history = llm.run_turn.call_args.args
    assert (ctx.chat_id, ctx.role, ctx.update_id, text) == (
        "42",
        "owner",
        9,
        "¿cuánto gasté hoy?",
    )
    assert ctx.now.tzinfo is not None
    body = json.loads(tg.calls.last.request.read())
    assert body["reply_markup"]["inline_keyboard"][0][0]["callback_data"] == "ok:t"
    st.add_llm_spend.assert_called_once_with("42", Decimal("0.001"))
    st.append_history.assert_called_once_with("42", llm.result.messages)
    record_args = llm.record.call_args.args
    assert record_args[0] is llm.result and record_args[2] == "¿cuánto gasté hoy?"


def test_rate_limit_skips_llm(st, llm, tg) -> None:
    st.check_rate.return_value = False
    assert client.post("/push", json=envelope(message())).status_code == 204
    llm.run_turn.assert_not_called()
    assert sent_texts(tg) == [t("es", "limit")]


def test_daily_cap_skips_llm(st, llm, tg) -> None:
    st.llm_spend_today.return_value = Decimal("0.10")
    assert client.post("/push", json=envelope(message())).status_code == 204
    llm.run_turn.assert_not_called()
    assert sent_texts(tg) == [t("es", "limit")]


def test_llm_unavailable_503(st, llm, tg) -> None:
    llm.run_turn.side_effect = LLMUnavailable()
    assert client.post("/push", json=envelope(message())).status_code == 503
    st.add_llm_spend.assert_not_called()
    assert not tg.calls


def test_telegram_failure_still_accounts(st, llm, tg, caplog) -> None:
    tg.post(f"{TG}/sendMessage").mock(return_value=httpx.Response(403))
    assert client.post("/push", json=envelope(message())).status_code == 204
    st.add_llm_spend.assert_called_once()
    assert "send_failed" in caplog.text


def test_start_and_non_text_skip_llm(st, llm, tg) -> None:
    client.post("/push", json=envelope(message("/start abc")))
    client.post("/push", json=envelope(message("")))
    llm.run_turn.assert_not_called()
    assert sent_texts(tg) == [
        t("es", "welcome"),
        t("es", "currency_question"),
        t("es", "text_only"),
    ]


def test_start_in_phone_language_clears_the_dashboard(
    monkeypatch, st, llm, tg, settings
):
    set_lang = MagicMock()
    monkeypatch.setattr(state, "set_lang", set_lang)
    update = message("/start abc")
    update["message"]["from"] = {"id": 42, "language_code": "en-US"}
    client.post("/push", json=envelope(update))
    assert sent_texts(tg) == [t("en", "welcome"), t("en", "currency_question")]
    assert sent_texts(tg)[0].startswith("Hi 🫶 I'm Juani")
    welcome = json.loads(tg.calls[0].request.read())
    assert welcome["reply_markup"] == {
        "inline_keyboard": [[{"text": "🗺️ Full guide", "url": worker.GUIDE_URL}]]
    }
    set_lang.assert_called_once_with("42", "en")
    paths = [c.request.url.path.rsplit("/", 1)[1] for c in tg.calls]
    assert paths == [
        "sendMessage",
        "setChatMenuButton",
        "unpinAllChatMessages",
        "sendMessage",
    ]
    menu = json.loads(tg.calls[1].request.read())["menu_button"]
    assert menu == {"type": "default"}
    st.get_user.return_value = {"idioma": "zh"}  # stored and unchanged: no write
    update["message"]["from"]["language_code"] = "zh-hans"
    client.post("/push", json=envelope(update))
    assert sent_texts(tg)[-2:] == [t("zh", "welcome"), t("zh", "currency_question")]
    set_lang.assert_called_once()


def test_start_asks_the_currency_with_buttons(st, llm, tg) -> None:
    client.post("/push", json=envelope(message("/start")))
    question = json.loads(tg.calls.last.request.read())
    assert question["text"] == t("es", "currency_question")
    assert question["reply_markup"]["inline_keyboard"] == [
        [
            {"text": "🇺🇸 USD", "callback_data": "mo:USD"},
            {"text": "🇪🇺 EUR", "callback_data": "mo:EUR"},
            {"text": "🇨🇴 COP", "callback_data": "mo:COP"},
            {"text": "🇨🇳 CNY", "callback_data": "mo:CNY"},
        ]
    ]


def test_currency_command_and_buttons(monkeypatch, st, llm, tg) -> None:
    set_currency = MagicMock()
    monkeypatch.setattr(state, "set_currency", set_currency)
    for text in ("/moneda", "Moneda", "currency", "/moneda xyz"):
        client.post("/push", json=envelope(message(text)))
    assert sent_texts(tg) == [t("es", "currency_question")] * 4
    set_currency.assert_not_called()
    client.post("/push", json=envelope(message("/moneda cop")))
    set_currency.assert_called_once_with("42", "COP")
    assert sent_texts(tg)[-1] == "✓ Moneda: COP. Tus montos se muestran en COP."
    st.get_user.return_value = {"rol": "beta", "idioma": "en"}
    client.post("/push", json=envelope(callback("mo:EUR")))
    set_currency.assert_called_with("42", "EUR")
    assert sent_texts(tg)[-1] == t("en", "currency_ok", currency="EUR")
    client.post("/push", json=envelope(callback("mo:XYZ")))  # not offered: ignored
    assert set_currency.call_count == 2
    llm.run_turn.assert_not_called()


def test_currency_failure_is_reported(monkeypatch, st, tg) -> None:
    monkeypatch.setattr(state, "set_currency", MagicMock(side_effect=RuntimeError))
    client.post("/push", json=envelope(callback("mo:CNY")))
    assert sent_texts(tg) == [t("es", "failed")]


def test_unknown_user_ignored(st, llm, tg) -> None:
    st.get_user.return_value = None
    assert client.post("/push", json=envelope(message())).status_code == 204
    assert not tg.calls


def test_callback_ok(monkeypatch, st, tg) -> None:
    execute = MagicMock(return_value="Hecho.")
    fake_module(monkeypatch, "assistant.llm.tools", execute_pending=execute)
    assert client.post("/push", json=envelope(callback("ok:tok"))).status_code == 204
    assert execute.call_args.args[1] == "tok"
    assert tg.routes[1].called
    assert sent_texts(tg) == ["Hecho."]


def test_callback_no(st, tg, caplog) -> None:
    tg.post(f"{TG}/answerCallbackQuery").mock(return_value=httpx.Response(400))
    assert client.post("/push", json=envelope(callback("no:tok"))).status_code == 204
    st.pop_pending.assert_called_once_with("42", "tok")
    assert sent_texts(tg) == ["Cancelado."]
    assert "answer_callback_failed" in caplog.text


def test_callback_unknown_action(st, tg) -> None:
    assert client.post("/push", json=envelope(callback("zz"))).status_code == 204
    assert sent_texts(tg) == []


def test_unexpected_turn_error_is_acknowledged(st, llm, tg) -> None:
    # A retry would pay for the turn again and could repeat a write.
    llm.run_turn.side_effect = RuntimeError("sheets down")
    assert client.post("/push", json=envelope(message())).status_code == 204
    assert sent_texts(tg) == [t("es", "failed")]
    st.add_llm_spend.assert_not_called()


# --- commands without the LLM ----------------------------------------------------


@pytest.fixture
def settings(monkeypatch):
    s = dataclasses.replace(get_worker_settings(), api_url="https://api.example")
    monkeypatch.setattr(worker, "get_worker_settings", lambda: s)
    return s


def keyboards(tg) -> list[list[tuple[str, str]]]:
    """Each sent message's buttons, flattened: (label, callback data or url)."""
    out = []
    for c in tg.calls:
        if c.request.url.path.endswith("sendMessage"):
            rows = json.loads(c.request.read()).get("reply_markup", {})
            out.append(
                [
                    (b["text"], b.get("url") or b["callback_data"])
                    for row in rows.get("inline_keyboard", [])
                    for b in row
                ]
            )
    return out


def test_calendar_lists_week_without_llm(monkeypatch, st, llm, tg) -> None:
    week = MagicMock(return_value="Jue 1 · 09:00 Dentista")
    monkeypatch.setattr(agenda, "week_text", week)
    assert (
        client.post("/push", json=envelope(message("/calendario"))).status_code == 204
    )
    week.return_value = "Sin nada en 7 días."
    st.get_preferences.return_value = {"gcal_token_enc": "x"}
    client.post("/push", json=envelope(message("/calendario@botjonh_bot")))
    st.get_preferences.return_value = {"ics_url_enc": "x"}
    client.post("/push", json=envelope(message("calendar")))
    assert sent_texts(tg) == ["Jue 1 · 09:00 Dentista", *["Sin nada en 7 días."] * 2]
    assert keyboards(tg) == [
        [("🪢 Conectar calendario", "cal:menu")],
        [("✂️ Desconectar Google", "cal:off")],
        [("✂️ Desconectar iPhone / Outlook", "cal:off")],
    ]
    assert week.call_args.args[0].chat_id == "42"
    llm.run_turn.assert_not_called()
    st.check_rate.assert_not_called()


@pytest.fixture
def cal_settings(monkeypatch, settings):
    s = dataclasses.replace(
        settings,
        kms_key="k",
        google_client_id="cid",
        google_client_secret="cs",  # pragma: allowlist secret
    )
    monkeypatch.setattr(worker, "get_worker_settings", lambda: s)
    return s


def test_calendar_buttons(monkeypatch, st, llm, tg, cal_settings) -> None:
    monkeypatch.setattr(state, "create_oauth_state", lambda chat_id: "s" * 22)
    tokens = iter(["a" * 32, "b" * 32])
    current: list[str] = []

    def ics_token(chat_id, rotate=False):
        if rotate or not current:
            current[:] = [next(tokens)]
        return current[0]

    monkeypatch.setattr(state, "ics_token", ics_token)
    disconnect = MagicMock()
    fake_module(monkeypatch, "assistant.services.gcal", disconnect=disconnect)
    for data in ("cal:menu", "cal:g", "cal:i", "cal:off"):
        client.post("/push", json=envelope(callback(data)))
    client.post("/push", json=envelope(message("/calendario nuevo")))
    assert sent_texts(tg) == [
        "¿Qué calendario usas?",
        t("es", "cal_google"),
        t("es", "cal_ical"),
        "Calendario desconectado.",
        t("es", "cal_ical"),
    ]
    assert keyboards(tg) == [
        [("Google", "cal:g"), ("iPhone / Outlook", "cal:i")],
        [("Conectar con Google", f"https://api.example/oauth/google?s={'s' * 22}")],
        [("🗓️ Suscribirme", f"https://api.example/ics/{'a' * 32}/suscribir")],
        [],
        [("🗓️ Suscribirme", f"https://api.example/ics/{'b' * 32}/suscribir")],
    ]
    disconnect.assert_called_once_with("42")
    llm.run_turn.assert_not_called()


def test_calendar_unconfigured_and_errors(monkeypatch, st, llm, tg, settings) -> None:
    client.post("/push", json=envelope(callback("cal:g")))  # no OAuth client
    unset = dataclasses.replace(get_worker_settings(), api_url="")
    monkeypatch.setattr(worker, "get_worker_settings", lambda: unset)
    client.post("/push", json=envelope(callback("cal:i")))
    monkeypatch.setattr(agenda, "week_text", MagicMock(side_effect=RuntimeError("x")))
    client.post("/push", json=envelope(message("/calendario")))
    assert sent_texts(tg) == [
        "Aún no disponible.",
        "Enlace no configurado.",
        t("es", "failed"),
    ]


# --- quick entry, ledger commands and GIFs (no LLM) ------------------------------


@pytest.fixture
def ledger(monkeypatch):
    return fake_module(
        monkeypatch,
        "assistant.services.ledger",
        record_expense=MagicMock(return_value="−2.00 USD · cafe"),
        record_income=MagicMock(return_value="+1000.00 USD · salario"),
        latest_text=MagicMock(return_value="1. cafe 2.00 USD"),
        void=MagicMock(return_value="✓ anulado"),
        reaction_key=MagicMock(return_value=""),
    )


def animations(tg, method: str = "sendAnimation") -> list[dict]:
    return [
        json.loads(c.request.read())
        for c in tg.calls
        if c.request.url.path.endswith(method)
    ]


def test_quick_expense_skips_llm_and_sends_gif(st, llm, tg, ledger, pick) -> None:
    st.get_user.return_value = {"fun": True}
    pick.return_value = GIF
    ledger.reaction_key.return_value = "restaurantes"
    assert (
        client.post("/push", json=envelope(message("2000 cop cafe"))).status_code == 204
    )
    ctx = ledger.record_expense.call_args.args[0]
    assert ledger.record_expense.call_args.kwargs == {
        "items": [
            {"amount": Decimal(2000), "category": "restaurantes", "note": "café"}
        ],
        "currency": "COP",
        "day": ctx.now.date(),
    }
    assert sent_texts(tg) == []  # the GIF is the whole answer
    assert animations(tg) == [{"chat_id": "42", "animation": GIF[0]}]
    ledger.reaction_key.assert_called_once_with("42", 9, "gasto")
    pick.assert_called_once_with("gasto", "restaurantes")
    llm.run_turn.assert_not_called()
    st.check_rate.assert_not_called()
    st.add_llm_spend.assert_not_called()
    st.append_history.assert_not_called()


def test_quick_income_without_gif_stored(st, llm, tg, ledger, pick) -> None:
    client.post("/push", json=envelope(message("ingreso 1000 salario")))
    kwargs = ledger.record_income.call_args.kwargs
    assert (kwargs["amount"], kwargs["currency"], kwargs["source"]) == (
        Decimal(1000),
        "USD",
        "salario",
    )
    fixed = "+1000.00 USD · salario"
    assert sent_texts(tg) == [fixed] and animations(tg) == []
    pick.assert_not_called()  # /fun off: no catalog lookup
    llm.run_turn.assert_not_called()


def test_quick_without_currency_uses_the_user_one(st, llm, tg, ledger) -> None:
    st.get_user.return_value = {"moneda": "COP"}
    client.post("/push", json=envelope(message("-25000 mercado")))
    assert ledger.record_expense.call_args.kwargs["currency"] == "COP"
    client.post("/push", json=envelope(message("-3 usd cafe")))  # typed wins
    assert ledger.record_expense.call_args.kwargs["currency"] == "USD"
    client.post("/push", json=envelope(message("5")))  # bare amount: the question
    assert sent_texts(tg)[-1] == "¿5.00 COP: gasto o ingreso?"
    llm.run_turn.assert_not_called()


def test_quick_errors_never_5xx(st, llm, tg, ledger, caplog, pick) -> None:
    client.post("/push", json=envelope(message("0 cafe")))
    ledger.record_expense.assert_not_called()
    ledger.record_expense.side_effect = RuntimeError("down")
    assert client.post("/push", json=envelope(message("cafe 5"))).status_code == 204
    ledger.record_expense.side_effect = None
    st.get_user.return_value = {"fun": True}
    pick.return_value = GIF
    tg.post(f"{TG}/sendAnimation").mock(return_value=httpx.Response(400))
    assert client.post("/push", json=envelope(message("cafe 7"))).status_code == 204
    assert sent_texts(tg) == [
        "El monto debe ser mayor que 0.",
        t("es", "failed"),
        "−2.00 USD · cafe",  # GIF failed: text fallback
    ]
    assert "react_failed" in caplog.text and "g.gif" not in caplog.text
    assert "cafe" not in caplog.text
    llm.run_turn.assert_not_called()


def test_llm_registration_sends_photo(st, llm, tg, ledger, pick) -> None:
    st.get_user.return_value = {"fun": True}
    pick.return_value = ("https://storage.googleapis.com/b/media/p.jpg", "foto")
    ledger.reaction_key.return_value = "salario"
    llm.result.keyboard = None
    llm.result.tools = ["record_income"]
    client.post("/push", json=envelope(message("me pagaron el freelance")))
    pick.assert_called_once_with("ingreso", "salario")
    assert animations(tg, "sendPhoto") == [
        {"chat_id": "42", "photo": "https://storage.googleapis.com/b/media/p.jpg"}
    ]
    llm.result.keyboard = [[("Sí", "ok:t")]]  # pending confirmation: no GIF yet
    llm.result.tools = ["record_expense"]
    client.post("/push", json=envelope(message("vuelo de 900 ayer")))
    assert len(animations(tg, "sendPhoto")) == 1


def test_void_asks_then_runs_on_ok(monkeypatch, st, llm, tg, ledger) -> None:
    token = "t" * 22
    client.post("/push", json=envelope(message("/anular 1")))
    client.post("/push", json=envelope(message("/anular")))
    ledger.void.assert_not_called()
    body = json.loads(tg.calls[0].request.read())
    assert body["text"] == "¿Anulo el movimiento 1?"
    assert body["reply_markup"]["inline_keyboard"][0][0]["callback_data"] == (
        f"ok:{token}"
    )
    assert st.create_pending.call_args.args[1] == {
        "tool": "void_entry",
        "args": {"index": 1},
    }
    st.pop_pending.return_value = st.create_pending.call_args.args[1]
    client.post("/push", json=envelope(callback(f"ok:{token}")))
    ledger.void.assert_called_once()
    assert ledger.void.call_args.kwargs == {"index": 1}
    assert sent_texts(tg)[1:] == [t("es", "void_usage"), "✓ anulado"]


def test_a_gif_from_the_user_is_not_understood(st, llm, tg) -> None:
    gif = {"update_id": 11, "message": {"chat": {"id": 42}}}
    gif["message"]["animation"] = {"file_id": "g1"}
    client.post("/push", json=envelope(gif))
    assert sent_texts(tg) == [t("es", "text_only")]
    llm.run_turn.assert_not_called()


def test_catalogo_opens_the_mini_app_for_the_owner_only(
    monkeypatch, st, llm, tg
) -> None:
    s = dataclasses.replace(get_worker_settings(), api_url="https://api.example")
    monkeypatch.setattr(worker, "get_worker_settings", lambda: s)
    client.post("/push", json=envelope(message("/catalogo")))
    body = json.loads(tg.calls[0].request.read())
    button = body["reply_markup"]["inline_keyboard"][0][0]
    assert button["web_app"]["url"].endswith("/catalogo")
    st.get_user.return_value = {**st.get_user.return_value, "rol": "beta"}
    client.post("/push", json=envelope(message("/catalogo")))
    assert sent_texts(tg)[-1] == state.OWNER_ONLY
    llm.run_turn.assert_not_called()


# --- reminders from Cloud Tasks --------------------------------------------------


def test_reminder_sends_for_active(monkeypatch, tg) -> None:
    reminder_text = MagicMock(return_value="🛎️ Dentista 09:00")
    monkeypatch.setattr(agenda, "reminder_text", reminder_text)
    body = {"chat_id": "42", "evento_id": "100"}
    assert client.post("/tasks/reminder", json=body).status_code == 204
    reminder_text.assert_called_once_with("42", "100", 0)
    assert sent_texts(tg) == ["🛎️ Dentista 09:00"]
    assert json.loads(tg.calls.last.request.read())["chat_id"] == "42"


def test_reminder_cancelled_or_malformed_is_204(monkeypatch, tg) -> None:
    monkeypatch.setattr(agenda, "reminder_text", MagicMock(return_value=None))
    body = {"chat_id": "42", "evento_id": "100"}
    assert client.post("/tasks/reminder", json=body).status_code == 204
    assert client.post("/tasks/reminder", content=b"{").status_code == 204
    assert client.post("/tasks/reminder", json={"x": 1}).status_code == 204
    assert not tg.calls


def test_reminder_telegram_error_is_not_5xx(monkeypatch, tg, caplog) -> None:
    monkeypatch.setattr(agenda, "reminder_text", MagicMock(return_value="🛎️ X 09:00"))
    tg.post(f"{TG}/sendMessage").mock(return_value=httpx.Response(500))
    body = {"chat_id": "42", "evento_id": "100"}
    assert client.post("/tasks/reminder", json=body).status_code == 204
    assert "reminder_send_failed" in caplog.text and "X 09:00" not in caplog.text


def test_bare_ical_url_connects_and_is_deleted(monkeypatch, st, llm, tg) -> None:
    connect = MagicMock(return_value="✓ Conectado.")
    busy = types.SimpleNamespace(connect=connect, validate_url=lambda raw: raw)
    monkeypatch.setitem(sys.modules, "assistant.services.busy", busy)
    url = "https://calendar.google.com/calendar/ical/x/private-y/basic.ics"
    update = message(url)
    update["message"]["message_id"] = 5
    client.post("/push", json=envelope(update))
    assert connect.call_args.args[1] == url
    deleted = [c for c in tg.calls if c.request.url.path.endswith("deleteMessage")]
    assert json.loads(deleted[0].request.read()) == {"chat_id": "42", "message_id": 5}
    assert sent_texts(tg) == ["✓ Conectado.\nBorré tu mensaje con el enlace."]
    llm.run_turn.assert_not_called()


def test_other_links_are_not_treated_as_calendars(monkeypatch, st, llm, tg) -> None:
    def validate_url(raw: str) -> str:
        raise ValueError("invalid_url")

    busy = types.SimpleNamespace(connect=MagicMock(), validate_url=validate_url)
    monkeypatch.setitem(sys.modules, "assistant.services.busy", busy)
    client.post("/push", json=envelope(message("https://example.com/x")))
    busy.connect.assert_not_called()


def test_bare_amount_asks_and_registers_the_chosen_type(
    monkeypatch, st, llm, tg, ledger
) -> None:
    pending: dict[str, dict] = {}

    def create(chat_id, action):
        pending["tok" + str(len(pending))] = action
        return "tok" + str(len(pending) - 1)

    st.create_pending.side_effect = create
    st.pop_pending.side_effect = lambda chat_id, t: pending.pop(t, None)
    st.random_gif.return_value = None
    client.post("/push", json=envelope(message("5")))
    asked = [
        json.loads(c.request.read())
        for c in tg.calls
        if c.request.url.path.endswith("sendMessage")
    ][-1]
    assert asked["text"] == "¿5.00 USD: gasto o ingreso?"
    buttons = asked["reply_markup"]["inline_keyboard"][0]
    assert [b["callback_data"] for b in buttons] == ["g:tok0", "i:tok0"]
    ledger.record_income.assert_not_called()
    client.post("/push", json=envelope(callback("i:tok0")))
    kwargs = ledger.record_income.call_args.kwargs
    assert (kwargs["amount"], kwargs["currency"], kwargs["source"]) == (
        Decimal("5.00"),
        "USD",
        "",
    )
    assert sent_texts(tg)[-1] == "+1000.00 USD · salario"
    client.post("/push", json=envelope(callback("g:tok0")))  # single use
    assert sent_texts(tg)[-1] == "La confirmación expiró."
    ledger.record_expense.assert_not_called()
    llm.run_turn.assert_not_called()


def test_invite_sends_a_deep_link_and_users_revokes(st, tg, monkeypatch) -> None:
    worker._bot_username.cache_clear()
    tg.post(f"{TG}/getMe").mock(
        return_value=httpx.Response(200, json={"result": {"username": "mi_bot"}})
    )
    create = MagicMock(return_value="c" * 22)
    today = datetime.now(ZoneInfo("America/Panama")).date()
    all_users = MagicMock(
        return_value=[
            ("1", {"nombre": "Yo", "rol": "owner", "ultimo_uso": today.isoformat()}),
            (
                "7",
                {
                    "nombre": "Ana",
                    "rol": "beta",
                    "ultimo_uso": str(today - timedelta(12)),
                },
            ),
            ("8", {"nombre": "Leo", "rol": "beta"}),
        ]
    )
    revoke = MagicMock(return_value=True)
    for name, m in (
        ("create_invite", create),
        ("all_users", all_users),
        ("revoke", revoke),
    ):
        monkeypatch.setattr(state, name, m)
    client.post("/push", json=envelope(message("/invitar Ana")))
    client.post("/push", json=envelope(message("/invitar")))
    client.post("/push", json=envelope(message("/usuarios")))
    client.post("/push", json=envelope(callback("rv:7")))
    texts = sent_texts(tg)
    assert texts[0].endswith("https://t.me/mi_bot?start=" + "c" * 22)
    assert texts[1:] == [
        worker.INVITE_USAGE,
        "3 usuarios · 1 activos en 7 días\n"
        "Yo (owner) · hoy\nAna (beta) · hace 12 días\nLeo (beta) · sin uso",
        "✓ Acceso revocado.",
    ]
    create.assert_called_once_with("Ana")
    revoke.assert_called_once_with("7")
    keyboards = [
        json.loads(c.request.read()).get("reply_markup")
        for c in tg.calls
        if c.request.url.path.endswith("sendMessage")
    ]
    assert keyboards[2] == {
        "inline_keyboard": [
            [{"text": "Revocar a Ana", "callback_data": "rv:7"}],
            [{"text": "Revocar a Leo", "callback_data": "rv:8"}],
        ]
    }


def test_owner_commands_refused_to_betas(st, tg, monkeypatch) -> None:
    st.get_user.return_value = {**st.get_user.return_value, "rol": "beta"}
    revoke = MagicMock()
    monkeypatch.setattr(state, "revoke", revoke)
    client.post("/push", json=envelope(message("/invitar Beto")))
    client.post("/push", json=envelope(callback("rv:1")))
    assert sent_texts(tg) == [state.OWNER_ONLY, "No se pudo revocar."]
    revoke.assert_not_called()


def test_dashboard_sends_viewer_and_pins_on_request(monkeypatch, st, llm, tg, settings):
    send = MagicMock(return_value=7)
    pin = MagicMock()
    monkeypatch.setattr(Telegram, "send_webapp", send)
    monkeypatch.setattr(Telegram, "pin", pin)
    client.post("/push", json=envelope(message("/tablero")))
    send.assert_called_once_with(
        "42", t("es", "dashboard"), "Visor de gastos", "https://api.example/visor"
    )
    pin.assert_not_called()
    for text in ("/tablero fijar", "Tablero fijar", "dashboard pin!"):
        client.post("/push", json=envelope(message(text)))
    assert [c.args for c in pin.call_args_list] == [("42", 7)] * 3
    assert send.call_count == 4
    assert sent_texts(tg) == []
    llm.run_turn.assert_not_called()


def test_plain_words_run_commands(monkeypatch, st, llm, tg, ledger) -> None:
    set_fun = MagicMock()
    monkeypatch.setattr(state, "set_fun", set_fun)
    for text in ("Ayuda", "  help. ", "Últimos", "FUN!"):
        client.post("/push", json=envelope(message(text)))
    texts = sent_texts(tg)
    assert texts[:2] == [t("es", "welcome")] * 2
    assert texts[3] == t("es", "fun_on")
    assert texts[2] == "1. cafe 2.00 USD"
    client.post("/push", json=envelope(message("ayuda con el arriendo")))
    llm.run_turn.assert_called_once()  # not a lone word: prose to the LLM


def test_summary_without_llm(monkeypatch, st, llm, tg) -> None:
    from assistant import jobs

    monkeypatch.setattr(jobs, "_checkin", lambda ctx: "hoy")
    monkeypatch.setattr(jobs, "_weekly", lambda ctx: "semana")
    client.post("/push", json=envelope(message("resumen")))
    monkeypatch.setattr(jobs, "_weekly", lambda ctx: None)
    client.post("/push", json=envelope(message("/resumen")))
    monkeypatch.setattr(jobs, "_checkin", MagicMock(side_effect=RuntimeError))
    client.post("/push", json=envelope(message("summary")))
    assert sent_texts(tg) == ["hoy\n\nsemana", "hoy", t("es", "failed")]
    llm.run_turn.assert_not_called()


def test_dashboard_unconfigured_and_errors(monkeypatch, st, llm, tg) -> None:
    unset = dataclasses.replace(get_worker_settings(), api_url="")
    monkeypatch.setattr(worker, "get_worker_settings", lambda: unset)
    client.post("/push", json=envelope(message("/tablero")))
    s = dataclasses.replace(unset, api_url="https://api.example")
    monkeypatch.setattr(worker, "get_worker_settings", lambda: s)
    send = MagicMock(side_effect=httpx.ConnectError("down"))
    monkeypatch.setattr(Telegram, "send_webapp", send)
    client.post("/push", json=envelope(message("/tablero")))
    assert sent_texts(tg) == ["Tablero no configurado.", t("es", "failed")]


def test_help_and_timezone(st, llm, tg, monkeypatch) -> None:
    set_timezone = MagicMock()
    monkeypatch.setattr(state, "set_timezone", set_timezone)
    for text in (
        "/ayuda",
        "/zona America/Bogota",
        "/zona Mars/Base",
        "/zona UTC",
        "/zona",
    ):
        client.post("/push", json=envelope(message(text)))
    usage = t("es", "tz_usage", tz="America/Panama")
    assert sent_texts(tg) == [
        t("es", "welcome"),
        "✓ Zona horaria: America/Bogota.",
        *[usage] * 3,
    ]
    set_timezone.assert_called_once_with("42", "America/Bogota")
    llm.run_turn.assert_not_called()


def test_fun_toggles_gif_replies(monkeypatch, st, llm, tg) -> None:
    set_fun = MagicMock()
    monkeypatch.setattr(state, "set_fun", set_fun)
    client.post("/push", json=envelope(message("/fun")))
    st.get_user.return_value = {"fun": True}
    client.post("/push", json=envelope(message("/fun")))
    assert [c.args for c in set_fun.call_args_list] == [("42", True), ("42", False)]
    assert sent_texts(tg) == [t("es", "fun_on"), t("es", "fun_off")]
    llm.run_turn.assert_not_called()


def test_registration_replies_without_a_correction_hint(st, llm, tg, ledger) -> None:
    llm.result.keyboard = None
    llm.result.tools = ["record_expense"]
    client.post("/push", json=envelope(message()))  # LLM path
    client.post("/push", json=envelope(message("cafe 5")))  # quick path
    assert sent_texts(tg) == [llm.result.reply, "−2.00 USD · cafe"]
    assert animations(tg) == []


def test_reset_asks_then_erases_data_and_recent_messages(monkeypatch, st, llm, tg):
    disconnect, reset_user = MagicMock(), MagicMock()
    fake_module(monkeypatch, "assistant.services.gcal", disconnect=disconnect)
    monkeypatch.setattr(state, "reset_user", reset_user)
    deleted = tg.post(f"{TG}/deleteMessages").mock(
        return_value=httpx.Response(200, json={"ok": True})
    )
    client.post("/push", json=envelope(message("Borrar todo")))
    no = callback("rs:no")
    client.post("/push", json=envelope(no))
    reset_user.assert_not_called()
    ok = callback("rs:ok")
    ok["callback_query"]["message"]["message_id"] = 150
    client.post("/push", json=envelope(ok))
    assert keyboards(tg)[0] == [
        (t("es", "reset_yes"), "rs:ok"),
        (t("es", "reset_no"), "rs:no"),
    ]
    assert sent_texts(tg)[1:] == [t("es", "cancelled"), t("es", "reset_done")]
    disconnect.assert_called_once_with("42")
    reset_user.assert_called_once_with("42")
    paths = [c.request.url.path.rsplit("/", 1)[1] for c in tg.calls]
    assert {"setChatMenuButton", "unpinAllChatMessages"} <= set(paths)
    batches = [json.loads(c.request.read())["message_ids"] for c in deleted.calls]
    assert [(b[0], b[-1]) for b in batches] == [(51, 150), (1, 50)]
    llm.run_turn.assert_not_called()


def test_latest_without_llm_and_editar_is_gone(st, llm, tg, ledger) -> None:
    client.post("/push", json=envelope(message("/ultimos")))
    assert sent_texts(tg) == ["1. cafe 2.00 USD"]
    assert ledger.latest_text.call_args.kwargs == {"n": 5}
    client.post("/push", json=envelope(message("editar: 15")))  # now plain text
    llm.run_turn.assert_called_once()


# --- photos ----------------------------------------------------------------------


@pytest.fixture
def photo(monkeypatch, tg):
    """A photo update; Telegram serves its file, Gemini is a fake module."""
    tg.post(f"{TG}/getFile").mock(
        return_value=httpx.Response(200, json={"result": {"file_path": "p/1.jpg"}})
    )
    tg.get(f"{API_BASE}/file/bot123:test/p/1.jpg").mock(
        return_value=httpx.Response(200, content=b"jpg")
    )
    photos = importlib.import_module("assistant.services.photos")
    fake = MagicMock(PhotoUnavailable=photos.PhotoUnavailable, split=photos.split)
    fake.save_split.return_value = "s1"
    fake.add_meal.return_value = "m1"
    fake.kcal_today.return_value = 900
    fake_module(
        monkeypatch,
        "assistant.services.photos",
        **{
            n: getattr(fake, n)
            for n in (
                "analyze",
                "add_meal",
                "kcal_today",
                "delete_meal",
                "save_split",
                "mark_paid",
                "open_splits",
            )
        },
        split=photos.split,
        PhotoUnavailable=photos.PhotoUnavailable,
    )
    return fake


def photo_update(caption: str = "") -> dict:
    msg = {"chat": {"id": 42}, "photo": [{"file_id": "s"}, {"file_id": "big"}]}
    return {"update_id": 11, "message": {**msg, "caption": caption}}


def test_meal_photo_is_saved_with_todays_total(st, llm, tg, photo) -> None:
    photo.analyze.return_value = {"kind": "meal", "name": "Arepa", "kcal": 300}
    assert client.post("/push", json=envelope(photo_update())).status_code == 204
    assert photo.analyze.call_args.args[0] == b"jpg"
    assert "Arepa · ~300 kcal" in sent_texts(tg)[0]
    assert "~900 kcal" in sent_texts(tg)[0]
    assert keyboards(tg) == [[("🗑️ Quitar", "ml:m1")]]
    llm.run_turn.assert_not_called()


def test_meal_tip_then_reaction_by_health(st, llm, tg, photo, pick) -> None:
    st.get_user.return_value = {"fun": True}
    pick.return_value = GIF
    photo.analyze.return_value = {
        "kind": "meal",
        "name": "Hamburguesa",
        "kcal": 900,
        "health": "unhealthy",
        "tip": "Cena verduras y proteína.",
    }
    client.post("/push", json=envelope(photo_update()))
    assert sent_texts(tg)[0].endswith("\n💡 Cena verduras y proteína.")
    pick.assert_called_once_with("comida", "chatarra")
    paths = [c.request.url.path.rsplit("/", 1)[1] for c in tg.calls]
    assert paths[-2:] == ["sendMessage", "sendAnimation"]  # text first
    st.get_user.return_value = {}  # /fun off: tip only
    client.post("/push", json=envelope(photo_update()))
    assert pick.call_count == 1


def test_receipt_with_people_is_split(st, llm, tg, photo) -> None:
    photo.analyze.return_value = {
        "kind": "receipt",
        "name": "Cena",
        "total": 200000,
        "currency": "cop",
        "people": 4,
    }
    client.post("/push", json=envelope(photo_update("cena salida 4")))
    assert photo.analyze.call_args.args[1] == "cena salida 4"
    text = sent_texts(tg)[0]
    assert "Cena: 200,000 COP entre 4" in text and "👤3: 50,000" in text
    assert keyboards(tg)[0][0] == ("✅ 👤1", "sp:s1:0")


def test_receipt_without_people_asks_how_many(st, llm, tg, photo) -> None:
    photo.analyze.return_value = {"kind": "receipt", "name": "Bar", "total": 90}
    client.post("/push", json=envelope(photo_update()))
    assert "¿Entre cuántos" in sent_texts(tg)[0]
    assert keyboards(tg)[0][0] == ("2", f"pp:{'t' * 22}:2")
    st.pop_pending.return_value = st.create_pending.call_args.args[1]
    client.post("/push", json=envelope(callback(f"pp:{'t' * 22}:3")))
    assert "Bar: 90 USD entre 3" in sent_texts(tg)[1]


def test_paid_button_settles_the_split(st, llm, tg, photo) -> None:
    photo.mark_paid.return_value = {"abierta": False, "titulo": "Cena"}
    client.post("/push", json=envelope(callback("sp:s1:0")))
    photo.mark_paid.assert_called_once_with("42", "s1", 0)
    assert sent_texts(tg) == [t("es", "split_settled", title="Cena")]


def test_cuentas_lists_who_owes(st, llm, tg, photo) -> None:
    photo.open_splits.return_value = [
        (
            "s1",
            {
                "titulo": "Cena",
                "fecha": "2026-10-07",
                "moneda": "COP",
                "deudores": [
                    {"nombre": "Ana", "monto": "50000", "pagado": False},
                    {"nombre": "👤1", "monto": "50000", "pagado": True},
                ],
            },
        ),
    ]
    client.post("/push", json=envelope(message("me deben")))
    assert sent_texts(tg) == ["Te deben:\n🧾 Cena (07/10): Ana 50,000 COP"]
    assert keyboards(tg) == [[("✅ Ana · Cena", "sp:s1:0")]]


def test_photo_failure_is_reported(st, llm, tg, photo) -> None:
    photo.analyze.side_effect = photo.PhotoUnavailable("x")
    client.post("/push", json=envelope(photo_update()))
    assert sent_texts(tg) == [t("es", "photo_unavailable")]


def test_meal_remove_button(st, llm, tg, photo) -> None:
    client.post("/push", json=envelope(callback("ml:m1")))
    photo.delete_meal.assert_called_once_with("42", "m1")
    assert sent_texts(tg) == [t("es", "meal_removed")]


def test_marks_the_active_day_once(st) -> None:
    st.get_user.return_value = {**st.get_user.return_value, "ultimo_uso": "2000-01-01"}
    client.post("/push", json=envelope(message("/ayuda")))
    (chat_id, day), _ = st.mark_seen.call_args
    assert chat_id == "42" and day != "2000-01-01"
    st.mark_seen.reset_mock()
    st.get_user.return_value["ultimo_uso"] = day
    client.post("/push", json=envelope(message("/ayuda")))
    st.mark_seen.assert_not_called()


def test_owner_answers_access_requests(st, tg, monkeypatch) -> None:
    req = {"nombre": "Ana", "idioma": "en"}
    accept = MagicMock(side_effect=[req, None])
    reject = MagicMock(return_value=req)
    monkeypatch.setattr(state, "accept_request", accept)
    monkeypatch.setattr(state, "reject_request", reject)
    for data in ("ap:7", "ap:7", "rj:8"):
        client.post("/push", json=envelope(callback(data)))
    assert sent_texts(tg) == [
        t("en", "access_granted"),
        "✓ Ana ya tiene acceso.",
        "Esa solicitud ya no está pendiente.",
        t("en", "access_rejected", days=10),
        "✓ Ana rechazado; puede volver a pedir en 10 días.",
    ]
    reject.assert_called_once_with("8")


def test_betas_cannot_answer_access_requests(st, tg, monkeypatch) -> None:
    st.get_user.return_value = {**st.get_user.return_value, "rol": "beta"}
    accept = MagicMock()
    monkeypatch.setattr(state, "accept_request", accept)
    client.post("/push", json=envelope(callback("ap:7")))
    accept.assert_not_called()
