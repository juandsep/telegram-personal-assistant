"""Google-only routes of the assistant service (see ``app.py``).

Push subscriber for assistant-updates (user messages) and assistant-cron
(scheduled jobs), and target of the Cloud Tasks reminders. The service is
public (Telegram reaches the webhook), so every route here requires the
Google-signed OIDC token checked by ``assistant.authz``.

Any 2xx acks the message; a 5xx makes Pub/Sub retry with backoff.
"""

from __future__ import annotations

import base64
import binascii
import dataclasses
import importlib
import json
import logging
import time
from datetime import date, datetime
from decimal import Decimal
from functools import cache
from typing import Any
from zoneinfo import ZoneInfo

import httpx
from fastapi import APIRouter, Depends, Request, Response
from fastapi.concurrency import run_in_threadpool

from assistant.authz import require_google_oidc
from assistant.channels.base import InboundMessage
from assistant.channels.telegram import Telegram, parse_update
from assistant.config import WorkerSettings, get_worker_settings
from assistant.context import ToolContext
from assistant.i18n import lang_of, t
from assistant.services import agenda, quick, state

logger = logging.getLogger(__name__)
router = APIRouter(dependencies=[Depends(require_google_oidc)])

ACK = 204
OWNER_COMMANDS = ("/invitar", "/usuarios")
INVITE_USAGE = "Uso: /invitar <nombre>. Crea un enlace de un uso, válido 24 h."
LEDGER_COMMANDS = ("/ultimos", "/anular")
RECORD_TOOLS = {"record_expense": "gasto", "record_income": "ingreso"}
GUIDE_URL = "https://juandsep.github.io/telegram-personal-assistant/guia/"
# A whole message of just these words (any case or accents) runs the command.
WORDS = {
    "tablero": "/tablero",
    "dashboard": "/tablero",
    "tablero fijar": "/tablero fijar",
    "dashboard pin": "/tablero fijar",
    "resumen": "/resumen",
    "summary": "/resumen",
    "ultimos": "/ultimos",
    "last": "/ultimos",
    "ayuda": "/ayuda",
    "help": "/ayuda",
    "calendario": "/calendario",
    "calendar": "/calendario",
    "agenda": "/calendario",
    "fun": "/fun",
    "moneda": "/moneda",
    "currency": "/moneda",
    "cuentas": "/cuentas",
    "splits": "/cuentas",
    "me deben": "/cuentas",
    "reset": "/reset",
    "reiniciar": "/reset",
    "borrar todo": "/reset",
}
RESET_BUTTONS = "rs:ok", "rs:no"
# Telegram lets a bot delete messages only for 48 h; older ones are skipped.
RESET_SCAN = 1000
# Display currencies: /moneda and the onboarding buttons.
CURRENCIES = {"USD": "🇺🇸 USD", "EUR": "🇪🇺 EUR", "COP": "🇨🇴 COP", "CNY": "🇨🇳 CNY"}
CURRENCY_BUTTONS = [[(label, f"mo:{cur}") for cur, label in CURRENCIES.items()]]
PEOPLE_CHOICES = range(2, 7)
# Gemini's verdict on a meal photo -> the comida/<key> reaction tag.
MEAL_REACTION = {"healthy": "sana", "meh": "meh", "unhealthy": "chatarra"}


@router.post("/push")
async def push(request: Request) -> Response:
    try:
        envelope = json.loads(await request.body())
        payload = json.loads(base64.b64decode(envelope["message"]["data"]))
    except (ValueError, KeyError, TypeError, binascii.Error):
        # Malformed: ack so Pub/Sub does not retry it forever.
        logger.warning("malformed_envelope")
        return Response(status_code=ACK)
    return Response(status_code=await run_in_threadpool(_route, payload))


@router.post("/tasks/reminder")
async def reminder(request: Request) -> Response:
    """Cloud Tasks at the reminder time. Always 2xx unless Firestore fails."""
    try:
        body = json.loads(await request.body())
        chat_id, event_id = str(body["chat_id"]), str(body["evento_id"])
        version = int(body.get("version", 0))
    except (ValueError, KeyError, TypeError, AttributeError):
        logger.warning("malformed_task")
        return Response(status_code=ACK)
    await run_in_threadpool(_remind, chat_id, event_id, version)
    return Response(status_code=ACK)


def _remind(chat_id: str, event_id: str, version: int) -> None:
    text = agenda.reminder_text(chat_id, event_id, version)
    if text is None:  # cancelled, moved or missing
        return
    try:
        Telegram(get_worker_settings().telegram_bot_token).send_message(chat_id, text)
    except httpx.HTTPError:
        logger.warning("reminder_send_failed")
        return
    logger.info("reminder_sent")


def _warm(settings: WorkerSettings) -> None:
    """Scheduler ping in waking hours: the push keeps this worker's instance
    alive and the GET keeps the api's (a cold start of both costs ~10 s)."""
    if not settings.api_url:
        return
    try:
        httpx.get(f"{settings.api_url}/health", timeout=15)
    except httpx.HTTPError:
        logger.warning("warm_api_failed")


def _route(payload: Any) -> int:
    if isinstance(payload, dict) and payload.get("job") == "warm":
        _warm(get_worker_settings())
        return ACK
    if isinstance(payload, dict) and "job" in payload:
        from assistant.jobs import run_job

        run_job(str(payload["job"]))
        return ACK
    msg = parse_update(payload)
    if msg is None:
        logger.warning("unsupported_update")
        return ACK
    return handle_update(msg, get_worker_settings())


def _context(user: dict, msg: InboundMessage, settings: WorkerSettings) -> ToolContext:
    tz = user.get("zona_horaria") or settings.default_timezone
    lang = user.get("idioma", "es")
    if msg.language_code and (new := lang_of(msg.language_code)) != lang:
        lang = new
        try:  # best effort: the phone's language, kept for the scheduled jobs
            state.set_lang(msg.chat_id, lang)
        except Exception as exc:
            logger.warning("idioma_failed error=%s", type(exc).__name__)
    return ToolContext(
        chat_id=msg.chat_id,
        role=user.get("rol", "beta"),
        currency=user.get("moneda", "USD"),
        timezone=tz,
        update_id=msg.update_id,
        now=datetime.now(ZoneInfo(tz)),
        lang=lang,
        fun=bool(user.get("fun")),
    )


def handle_update(msg: InboundMessage, settings: WorkerSettings) -> int:
    user = state.get_user(msg.chat_id)
    if user is None:  # removed after the api accepted it
        return ACK
    ctx = _context(user, msg, settings)
    today = ctx.now.date().isoformat()
    if user.get("ultimo_uso") != today:  # one write per user and day
        state.mark_seen(msg.chat_id, today)
    channel = Telegram(settings.telegram_bot_token)
    if msg.callback_query_id:
        return _callback(ctx, msg, msg.callback_query_id, channel)
    if cmd := WORDS.get(" ".join(quick.norm(msg.text).rstrip(".!? ").split())):
        msg = dataclasses.replace(msg, text=cmd)
    if msg.text.startswith("/zona"):
        _send(channel, msg, _timezone_command(ctx, msg))
        return ACK
    if msg.text.startswith("/moneda"):
        _send(channel, msg, *_currency_command(ctx, msg))
        return ACK
    if msg.text.startswith("/reset"):
        ok, no = RESET_BUTTONS
        buttons = [[(t(ctx.lang, "reset_yes"), ok), (t(ctx.lang, "reset_no"), no)]]
        _send(channel, msg, t(ctx.lang, "reset_question"), buttons)
        return ACK
    if msg.text.startswith(("/start", "/ayuda", "/help")):
        guide = [[(t(ctx.lang, "guide"), GUIDE_URL)]]
        _send(channel, msg, t(ctx.lang, "welcome"), guide)
        if msg.text.startswith("/start"):
            _clear_dashboard(channel, msg)  # the Visor only on /tablero
            _send(channel, msg, t(ctx.lang, "currency_question"), CURRENCY_BUTTONS)
        return ACK
    if msg.photo_file_id:
        if not state.check_rate(msg.chat_id, settings.max_msgs_per_minute):
            _send(channel, msg, t(ctx.lang, "limit"))
        else:
            if out := _photo(ctx, msg, channel, settings):
                _send(channel, msg, *out)
        return ACK
    if not msg.text.strip():
        _send(channel, msg, t(ctx.lang, "text_only"))
        return ACK
    if _is_ical_url(msg.text):  # the secret iCal link, sent on its own
        reply = _connect_ical(ctx, msg)
        if msg.message_id is not None:  # drop the secret from the chat
            try:
                channel.delete_message(msg.chat_id, msg.message_id)
                reply += "\nBorré tu mensaje con el enlace."
            except httpx.HTTPError:
                logger.warning("delete_failed update_id=%s", msg.update_id)
        _send(channel, msg, reply)
        return ACK
    if msg.text.startswith("/calendario"):
        arg = msg.text.partition(" ")[2]
        _send(channel, msg, *_calendar(ctx, msg, arg), remember=_calendar_note(arg))
        return ACK
    if msg.text.startswith("/catalogo"):
        _catalog(ctx, channel, msg, settings)
        return ACK
    if msg.text.startswith(OWNER_COMMANDS):
        _send(channel, msg, *_owner_command(ctx, msg, settings))
        return ACK
    if msg.text.startswith("/fun"):
        _send(channel, msg, _fun(ctx, msg))
        return ACK
    if msg.text.startswith("/tablero"):
        _dashboard(ctx, channel, msg, settings)
        return ACK
    if msg.text.startswith("/cuentas"):
        _send(channel, msg, *_splits(ctx, msg))
        return ACK
    if msg.text.startswith("/resumen"):
        _send(channel, msg, _summary(ctx, msg))
        return ACK
    if msg.text.startswith(LEDGER_COMMANDS):
        _send(channel, msg, *_ledger_command(ctx, msg))
        return ACK
    entry = quick.parse(msg.text, default=ctx.currency)
    if entry is not None:  # deterministic: no LLM, no spend, no history
        _quick(ctx, msg, entry, channel)
        return ACK

    # 1. Rate limit and daily cap: fail closed without calling the LLM.
    if not state.check_rate(msg.chat_id, settings.max_msgs_per_minute) or (
        state.llm_spend_today(msg.chat_id) >= settings.max_llm_usd_per_day
    ):
        logger.info("limit_reached update_id=%s", msg.update_id)
        _send(channel, msg, t(ctx.lang, "limit"))
        return ACK

    # 2. The turn. LLMUnavailable -> 503 so Pub/Sub retries with backoff.
    from assistant.llm import client

    started = time.monotonic()
    try:
        result = client.run_turn(ctx, msg.text, state.get_history(msg.chat_id))
    except client.LLMUnavailable:
        logger.warning("llm_unavailable update_id=%s", msg.update_id)
        return 503
    except Exception as exc:
        # Any other failure is acknowledged: a Pub/Sub retry would pay for the
        # turn again and could repeat a non-idempotent write.
        logger.error(
            "turn_failed update_id=%s error=%s", msg.update_id, type(exc).__name__
        )
        _send(channel, msg, t(ctx.lang, "failed"))
        return ACK

    # 3-5. Reply, account, trace.
    records = [RECORD_TOOLS[t] for t in result.tools if t in RECORD_TOOLS]
    recorded = bool(records) and not result.keyboard
    _send(channel, msg, result.reply, result.keyboard, remember=False)
    if recorded and ctx.fun:
        _react(channel, msg, records[-1])
    state.add_llm_spend(msg.chat_id, result.cost_usd)
    state.append_history(msg.chat_id, result.messages)
    from assistant.observability import trace

    trace.record_turn(result, int((time.monotonic() - started) * 1000), msg.text)
    return ACK


def _is_ical_url(text: str) -> bool:
    """A lone https/webcal link to an allowlisted calendar host."""
    text = text.strip()
    if " " in text or not text.lower().startswith(("https://", "webcal://")):
        return False
    try:
        importlib.import_module("assistant.services.busy").validate_url(text)
    except Exception:
        return False
    return True


def _connect_ical(ctx: ToolContext, msg: InboundMessage) -> str:
    try:
        busy = importlib.import_module("assistant.services.busy")
        return str(busy.connect(ctx, msg.text.strip()))
    except Exception as exc:
        logger.error(
            "command_failed update_id=%s error=%s", msg.update_id, type(exc).__name__
        )
        return t(ctx.lang, "failed")


def _calendar_note(arg: str) -> bool | str:
    """The 7-day list can hold the connected calendar's busy times, which never
    reach the LLM: its history gets a stand-in."""
    if arg.strip().lower() in ("menu", "g", "i", "nuevo", "off"):
        return True
    return "[Le mostré su agenda de los próximos 7 días con el botón del calendario.]"


def _calendar(
    ctx: ToolContext, msg: InboundMessage, arg: str
) -> tuple[str, list[list[tuple[str, str]]] | None]:
    """/calendario [off|nuevo] and its buttons cal:menu|g|i|off: the next 7 days,
    then one calendar, Google (OAuth) or iPhone/Outlook (ICS subscription)."""
    settings = get_worker_settings()
    arg = arg.strip().lower()
    try:
        if arg == "menu":
            buttons = [("Google", "cal:g"), ("iPhone / Outlook", "cal:i")]
            return t(ctx.lang, "cal_choose"), [buttons]
        if arg == "g":
            if not (
                settings.google_client_id
                and settings.google_client_secret
                and settings.api_url
                and settings.kms_key
            ):
                return t(ctx.lang, "unavailable"), None
            url = f"{settings.api_url}/oauth/google?s="
            url += state.create_oauth_state(ctx.chat_id)
            button = (t(ctx.lang, "cal_google_button"), url)
            return t(ctx.lang, "cal_google"), [[button]]
        if arg in ("i", "nuevo"):  # nuevo: a new feed link, the old one revoked
            if not settings.api_url:
                return t(ctx.lang, "link_not_configured"), None
            token = state.ics_token(ctx.chat_id, rotate=arg == "nuevo")
            url = f"{settings.api_url}/ics/{token}/suscribir"
            return t(ctx.lang, "cal_ical"), [[(t(ctx.lang, "cal_subscribe"), url)]]
        if arg == "off":
            importlib.import_module("assistant.services.gcal").disconnect(ctx.chat_id)
            return t(ctx.lang, "cal_disconnected"), None
        prefs = state.get_preferences(ctx.chat_id)
        if prefs.get("gcal_token_enc") or prefs.get("gcal_id"):
            button = (t(ctx.lang, "cal_disconnect", which="Google"), "cal:off")
        elif prefs.get("ics_url_enc"):
            which = "iPhone / Outlook"
            button = (t(ctx.lang, "cal_disconnect", which=which), "cal:off")
        else:
            button = (t(ctx.lang, "cal_connect"), "cal:menu")
        return agenda.week_text(ctx), [[button]]
    except Exception as exc:
        logger.error(
            "command_failed update_id=%s error=%s", msg.update_id, type(exc).__name__
        )
        return t(ctx.lang, "failed"), None


def _quick(
    ctx: ToolContext, msg: InboundMessage, entry: quick.Entry, channel: Telegram
) -> None:
    if entry.error:
        _send(channel, msg, t(ctx.lang, "positive"))
        return
    if not entry.kind:  # a bare amount: ask, register on the button
        from assistant.llm import tools

        try:
            question, keyboard = tools.ask_kind(ctx, entry.amount, entry.currency)
        except Exception as exc:
            logger.error(
                "quick_failed update_id=%s error=%s", msg.update_id, type(exc).__name__
            )
            _send(channel, msg, t(ctx.lang, "failed"))
            return
        _send(channel, msg, question, keyboard)
        return
    day = ctx.now.date()
    try:
        ledger = importlib.import_module("assistant.services.ledger")
        if entry.kind == "ingreso":
            reply = ledger.record_income(
                ctx,
                amount=entry.amount,
                currency=entry.currency,
                source=entry.note,
                day=day,
            )
        else:
            item = {
                "amount": entry.amount,
                "category": entry.category,
                "note": entry.note or None,
            }
            reply = ledger.record_expense(
                ctx, items=[item], currency=entry.currency, day=day
            )
    except Exception as exc:
        logger.error(
            "quick_failed update_id=%s error=%s", msg.update_id, type(exc).__name__
        )
        _send(channel, msg, t(ctx.lang, "failed"))
        return
    logger.info("quick_entry update_id=%s", msg.update_id)
    _send_record(ctx, channel, msg, str(reply))


def _send_record(
    ctx: ToolContext, channel: Telegram, msg: InboundMessage, reply: str
) -> None:
    """A registration answers with the entry as stored; with /fun on, with the
    reaction image only (the text is the fallback when the catalog has none)."""
    kind = {"−": "gasto", "+": "ingreso"}.get(reply[:1])
    if kind and ctx.fun and _react(channel, msg, kind):
        return
    _send(channel, msg, reply)


Keyboard = list[list[tuple[str, str]]] | None


def _photo(
    ctx: ToolContext, msg: InboundMessage, channel: Telegram, settings: WorkerSettings
) -> tuple[str, Keyboard] | None:
    """A meal (kcal, saved; sent here with its tip, then the reaction image) or a
    receipt (split, saved when the people count is known, else asked with
    buttons). None when already sent. The photo is not kept."""
    photos = importlib.import_module("assistant.services.photos")
    try:
        image = channel.download(str(msg.photo_file_id))
        data = photos.analyze(
            image, msg.caption, ctx, settings.gemini_api_key, settings.gemini_model
        )
        logger.info("photo update_id=%s kind=%s", msg.update_id, data.get("kind"))
        if data.get("kind") == "meal":
            meal_id = photos.add_meal(ctx, data)
            reply = t(
                ctx.lang,
                "meal",
                name=data.get("name") or "?",
                kcal=int(data.get("kcal") or 0),
                protein=int(data.get("protein_g") or 0),
                carbs=int(data.get("carbs_g") or 0),
                fat=int(data.get("fat_g") or 0),
                today=photos.kcal_today(ctx),
            )
            if tip := str(data.get("tip") or "").strip():
                reply += f"\n💡 {tip[:200]}"
            _send(
                channel, msg, reply, [[(t(ctx.lang, "meal_remove"), f"ml:{meal_id}")]]
            )
            tag = MEAL_REACTION.get(str(data.get("health")))
            if ctx.fun and tag:  # after the text, like a registration's reaction
                _react(channel, msg, "comida", tag)
            return None
        if data.get("kind") == "receipt" and Decimal(str(data.get("total") or 0)) > 0:
            receipt: dict[str, Any] = {
                "title": str(data.get("name") or "🧾"),
                "total": str(data["total"]),
                "currency": str(data.get("currency") or ctx.currency).upper()[:3],
                "items": [
                    {
                        "name": str(i.get("name", "")),
                        "price": str(i.get("price", 0)),
                        "person": str(i.get("person") or ""),
                    }
                    for i in data.get("items") or []
                ],
            }
            named = any(i["person"] for i in receipt["items"])
            if int(data.get("people") or 0) >= 2 or named:
                return _split(ctx, receipt, int(data.get("people") or 0))
            token = state.create_pending(ctx.chat_id, {"split": receipt})
            total = _money(Decimal(receipt["total"]))
            question = t(
                ctx.lang,
                "split_people",
                title=receipt["title"],
                total=total,
                currency=receipt["currency"],
            )
            return question, [[(str(n), f"pp:{token}:{n}") for n in PEOPLE_CHOICES]]
        return t(ctx.lang, "photo_other"), None
    except (photos.PhotoUnavailable, httpx.HTTPError) as exc:
        logger.warning(
            "photo_failed update_id=%s error=%s", msg.update_id, type(exc).__name__
        )
        return t(ctx.lang, "photo_unavailable"), None
    except Exception as exc:
        logger.error(
            "photo_failed update_id=%s error=%s", msg.update_id, type(exc).__name__
        )
        return t(ctx.lang, "failed"), None


def _money(value: Decimal) -> str:
    return str(importlib.import_module("assistant.services.ledger")._figure(value))


def _split(ctx: ToolContext, receipt: dict, people: int) -> tuple[str, Keyboard]:
    """Split a read receipt, save it and list the shares with ✅ buttons."""
    photos = importlib.import_module("assistant.services.photos")
    total = Decimal(receipt["total"])
    debtors = photos.split(total, people, receipt["items"])
    split_id = photos.save_split(
        ctx, receipt["title"], total, receipt["currency"], debtors
    )
    shares = "\n".join(f"{name}: {_money(amount)}" for name, amount in debtors)
    reply = t(
        ctx.lang,
        "split",
        title=receipt["title"],
        total=_money(total),
        currency=receipt["currency"],
        people=len(debtors) + 1,
        shares=shares,
    )
    buttons = [
        (f"✅ {name}", f"sp:{split_id}:{i}") for i, (name, _) in enumerate(debtors)
    ]
    return reply, [buttons[i : i + 3] for i in range(0, len(buttons), 3)]


def _splits(ctx: ToolContext, msg: InboundMessage) -> tuple[str, Keyboard]:
    """/cuentas: who still owes the owner, with a ✅ per unpaid share."""
    try:
        rows = importlib.import_module("assistant.services.photos").open_splits(
            ctx.chat_id
        )
    except Exception as exc:
        logger.error(
            "command_failed update_id=%s error=%s", msg.update_id, type(exc).__name__
        )
        return t(ctx.lang, "failed"), None
    if not rows:
        return t(ctx.lang, "split_none"), None
    lines, buttons = [t(ctx.lang, "split_pending")], []
    for split_id, d in rows:
        unpaid = [(i, x) for i, x in enumerate(d["deudores"]) if not x["pagado"]]
        owed = ", ".join(
            f"{x['nombre']} {_money(Decimal(x['monto']))}" for _, x in unpaid
        )
        day = f"{d['fecha'][8:]}/{d['fecha'][5:7]}"
        lines.append(f"🧾 {d['titulo']} ({day}): {owed} {d['moneda']}")
        buttons += [
            [(f"✅ {x['nombre']} · {d['titulo']}", f"sp:{split_id}:{i}")]
            for i, x in unpaid
        ]
    return "\n".join(lines), buttons[:20]


def _summary(ctx: ToolContext, msg: InboundMessage) -> str:
    """/resumen: today's spend, the week and the month vs income. No LLM."""
    try:
        from assistant import jobs

        parts = [jobs._checkin(ctx), jobs._weekly(ctx)]
    except Exception as exc:
        logger.error(
            "command_failed update_id=%s error=%s", msg.update_id, type(exc).__name__
        )
        return t(ctx.lang, "failed")
    return "\n\n".join(p for p in parts if p)


def _fun(ctx: ToolContext, msg: InboundMessage) -> str:
    """/fun toggles reaction images after registrations and meal photos."""
    try:
        state.set_fun(ctx.chat_id, not ctx.fun)
    except Exception as exc:
        logger.error(
            "command_failed update_id=%s error=%s", msg.update_id, type(exc).__name__
        )
        return t(ctx.lang, "failed")
    return t(ctx.lang, "fun_off" if ctx.fun else "fun_on")


def _clear_dashboard(channel: Telegram, msg: InboundMessage) -> None:
    """Best effort: the default menu button (older chats got the Visor there)
    and no pinned messages."""
    try:
        channel.clear_menu(msg.chat_id)
        channel.unpin_all(msg.chat_id)
    except httpx.HTTPError:
        logger.warning("clear_dashboard_failed update_id=%s", msg.update_id)


def _reset(ctx: ToolContext, msg: InboundMessage, channel: Telegram) -> str:
    """Erase the chat's data (access stays), forget its calendar and delete the
    recent messages of the chat, best effort."""
    try:
        importlib.import_module("assistant.services.gcal").disconnect(ctx.chat_id)
        state.reset_user(ctx.chat_id)
    except Exception as exc:
        logger.error(
            "reset_failed update_id=%s error=%s", msg.update_id, type(exc).__name__
        )
        return t(ctx.lang, "failed")
    logger.info("user_reset update_id=%s", msg.update_id)
    _clear_dashboard(channel, msg)
    last = msg.message_id or 0
    for top in range(last, max(last - RESET_SCAN, 0), -100):
        try:
            ids = list(range(max(top - 99, 1), top + 1))
            channel.delete_messages(ctx.chat_id, ids)
        except httpx.HTTPError:
            logger.warning("reset_delete_failed update_id=%s", msg.update_id)
    return t(ctx.lang, "reset_done")


def _timezone_command(ctx: ToolContext, msg: InboundMessage) -> str:
    """/zona America/Bogota: the time zone of the agenda and the reports."""
    tz = msg.text.strip().partition(" ")[2].strip()
    try:
        if not tz or "/" not in tz:
            raise ValueError
        ZoneInfo(tz)
    except (ValueError, KeyError):  # ZoneInfoNotFoundError is a KeyError
        return t(ctx.lang, "tz_usage", tz=ctx.timezone)
    state.set_timezone(ctx.chat_id, tz)
    logger.info("zona_set update_id=%s", msg.update_id)
    return t(ctx.lang, "tz_ok", tz=tz)


def _currency_command(
    ctx: ToolContext, msg: InboundMessage
) -> tuple[str, list[list[tuple[str, str]]] | None]:
    """/moneda COP sets it; without a valid code, the question with buttons."""
    cur = msg.text.strip().partition(" ")[2].strip().upper()
    if cur not in CURRENCIES:
        return t(ctx.lang, "currency_question"), CURRENCY_BUTTONS
    return _set_currency(ctx, msg, cur), None


def _set_currency(ctx: ToolContext, msg: InboundMessage, cur: str) -> str:
    try:
        state.set_currency(ctx.chat_id, cur)
    except Exception as exc:
        logger.error(
            "command_failed update_id=%s error=%s", msg.update_id, type(exc).__name__
        )
        return t(ctx.lang, "failed")
    logger.info("moneda_set update_id=%s moneda=%s", msg.update_id, cur)
    return t(ctx.lang, "currency_ok", currency=cur)


@cache
def _bot_username(bot_token: str) -> str:
    return Telegram(bot_token).username()


def _seen(days: int | None) -> str:
    if days is None:
        return "sin uso"
    return "hoy" if days <= 0 else "ayer" if days == 1 else f"hace {days} días"


def _answer_request(channel: Telegram, action: str, chat_id: str) -> str:
    """The owner's ✅/❌ on an access request; the requester is told either way."""
    if action == "ap":
        data = state.accept_request(chat_id)
        key, reply = "access_granted", "✓ {} ya tiene acceso."
    else:
        data = state.reject_request(chat_id)
        key = "access_rejected"
        reply = (
            f"✓ {{}} rechazado; puede volver a pedir en {state.REJECT_WAIT_DAYS} días."
        )
    if data is None:
        return "Esa solicitud ya no está pendiente."
    channel.send_message(chat_id, t(data["idioma"], key, days=state.REJECT_WAIT_DAYS))
    return reply.format(data["nombre"])


def _owner_command(
    ctx: ToolContext, msg: InboundMessage, settings: WorkerSettings
) -> tuple[str, list[list[tuple[str, str]]] | None]:
    """/invitar <nombre> (t.me deep link) and /usuarios (revoke buttons)."""
    if ctx.role != "owner":
        return state.OWNER_ONLY, None
    cmd, _, name = msg.text.strip().partition(" ")
    name = name.strip()
    if cmd.split("@")[0] == "/invitar":
        if not name or len(name) > 40:
            return INVITE_USAGE, None
        code = state.create_invite(name)
        logger.info("invite_created update_id=%s", msg.update_id)
        link = f"https://t.me/{_bot_username(settings.telegram_bot_token)}?start={code}"
        return f"Invitación para {name} (un uso, 24 h). Reenvíale:\n{link}", None
    rows = state.all_users()
    today = ctx.now.date()
    ages = [
        (today - date.fromisoformat(u["ultimo_uso"])).days
        if u.get("ultimo_uso")
        else None
        for _, u in rows
    ]
    active = sum(1 for a in ages if a is not None and a < 7)
    lines = [f"{len(rows)} usuarios · {active} activos en 7 días"] + [
        f"{u.get('nombre', '?')} ({u.get('rol', '?')}) · {_seen(a)}"
        for (_, u), a in zip(rows, ages, strict=True)
    ]
    text = "\n".join(lines) if rows else ""
    buttons = [
        [(f"Revocar a {u.get('nombre', '?')}", f"rv:{chat_id}")]
        for chat_id, u in rows
        if u.get("rol") == "beta"
    ]
    return text or "Sin usuarios.", buttons or None


def _ledger_command(
    ctx: ToolContext, msg: InboundMessage
) -> tuple[str, list[list[tuple[str, str]]] | None]:
    """/ultimos, /anular n (buttons): no LLM."""

    cmd, _, arg = msg.text.strip().partition(" ")
    cmd, arg = cmd.split("@")[0], arg.strip()
    n, _, rest = arg.partition(" ")
    usage = t(ctx.lang, "void_usage")
    args: dict[str, Any] = {"index": int(n)} if n.isdecimal() else {}
    if cmd == "/ultimos":
        name, args = "latest_entries", {"n": 5}
    elif cmd == "/anular" and args and not rest:
        name = "void_entry"
    else:
        return usage, None
    return _tool(ctx, msg, name, args, usage)


def _tool(
    ctx: ToolContext, msg: InboundMessage, name: str, args: dict, usage: str
) -> tuple[str, list[list[tuple[str, str]]] | None]:
    """One tool call without the LLM; usage when the arguments are rejected."""
    from assistant.llm import tools

    try:  # same validation as the LLM path; Decimal goes as an exact string
        reply, token = tools.handle_call(ctx, name, json.dumps(args, default=str))
    except tools.ToolRejected:  # amount <= 0, index out of range
        return usage, None
    except Exception as exc:
        logger.error(
            "command_failed update_id=%s error=%s", msg.update_id, type(exc).__name__
        )
        return t(ctx.lang, "failed"), None
    return reply, tools.buttons(token) if token else None


def _dashboard(
    ctx: ToolContext, channel: Telegram, msg: InboundMessage, settings: WorkerSettings
) -> None:
    """/tablero: the dashboard Mini App (the service's /visor); /tablero fijar
    also pins it in the chat."""
    if not settings.api_url:
        _send(channel, msg, t(ctx.lang, "dashboard_not_configured"))
        return
    try:
        message_id = channel.send_webapp(
            msg.chat_id,
            t(ctx.lang, "dashboard"),
            t(ctx.lang, "viewer"),
            f"{settings.api_url}/visor",
        )
        if msg.text.split()[1:] in (["fijar"], ["pin"]):
            channel.pin(msg.chat_id, message_id)
    except httpx.HTTPError:
        logger.warning("pin_failed update_id=%s", msg.update_id)
        _send(channel, msg, t(ctx.lang, "failed"))


def _catalog(
    ctx: ToolContext, channel: Telegram, msg: InboundMessage, settings: WorkerSettings
) -> None:
    """/catalogo (owner): the Mini App that uploads reaction images."""
    if ctx.role != "owner":
        _send(channel, msg, state.OWNER_ONLY)
        return
    if not settings.api_url:
        _send(channel, msg, t(ctx.lang, "dashboard_not_configured"))
        return
    try:
        channel.send_webapp(
            msg.chat_id,
            "Sube imágenes y GIFs y elige su etiqueta 🖼️",
            "Catálogo",
            f"{settings.api_url}/catalogo",
        )
    except httpx.HTTPError:
        logger.warning("send_failed update_id=%s", msg.update_id)


def _react(
    channel: Telegram, msg: InboundMessage, kind: str, key: str | None = None
) -> bool:
    """Best effort reaction image from the catalog; False when none was sent.
    A registration's categoria/fuente picks the tag, else ``<kind>/general``."""
    try:
        if key is None:
            ledger = importlib.import_module("assistant.services.ledger")
            key = ledger.reaction_key(msg.chat_id, msg.update_id, kind)
        media = importlib.import_module("assistant.services.media")
        item = media.pick(kind, key)
        if item:
            url, tipo = item
            if tipo == "gif":
                channel.send_animation(msg.chat_id, url)
            else:
                channel.send_photo(msg.chat_id, url)
            return True
    except Exception as exc:
        logger.warning(
            "react_failed update_id=%s error=%s", msg.update_id, type(exc).__name__
        )
    return False


def _send(
    channel: Telegram,
    msg: InboundMessage,
    text: str,
    keyboard: Any = None,
    remember: bool | str = True,
) -> None:
    """Best effort: a Telegram error must not make Pub/Sub rerun a paid turn.

    Replies that skip the LLM (commands, buttons, quick entries, photos) go to
    the LLM history too, so a follow-up ("¿ya quedó?") has context. ``remember``
    is False for the LLM's own reply (its turn is stored whole) or a stand-in
    text when the reply holds data the LLM must not see."""
    try:
        channel.send_message(msg.chat_id, text, keyboard)
    except httpx.HTTPError:
        logger.warning("send_failed update_id=%s", msg.update_id)
    if remember is False:
        return
    reply = text if remember is True else remember
    try:
        state.append_history(
            msg.chat_id,
            [
                {"role": "user", "content": _said(msg)},
                {"role": "assistant", "content": reply[:800]},
            ],
        )
    except Exception as exc:  # context is a nicety; the reply already went out
        logger.warning("history_failed error=%s", type(exc).__name__)


def _said(msg: InboundMessage) -> str:
    """What the user did, for the LLM history, without secrets."""
    if msg.callback_query_id:
        return f"[Tocó el botón {msg.callback_data}]"
    if msg.photo_file_id:
        return f"[Envió una foto] {msg.caption}".strip()
    if _is_ical_url(msg.text):
        return "[Envió su enlace iCal privado]"
    if msg.text.startswith("/start"):
        return "/start"  # never an invite code
    return msg.text[:500]


def _photo_button(
    ctx: ToolContext, msg: InboundMessage, action: str, token: str
) -> tuple[str, Keyboard]:
    """ml:<meal> removes a meal; sp:<split>:<i> marks a share paid; pp:<token>:<n>
    splits a pending receipt between n people."""
    photos = importlib.import_module("assistant.services.photos")
    key, _, arg = token.partition(":")
    try:
        if action == "ml":
            photos.delete_meal(ctx.chat_id, key)
            return t(ctx.lang, "meal_removed"), None
        if action == "pp":
            pending = state.pop_pending(ctx.chat_id, key)
            if not pending or not arg.isdecimal():
                return t(ctx.lang, "cancelled"), None
            return _split(ctx, pending["split"], int(arg))
        split = photos.mark_paid(ctx.chat_id, key, int(arg) if arg.isdecimal() else -1)
        if split is None:
            return t(ctx.lang, "cancelled"), None
        if not split["abierta"]:
            return t(ctx.lang, "split_settled", title=split["titulo"]), None
        return _splits(ctx, msg)
    except Exception as exc:
        logger.error(
            "photo_button_failed update_id=%s error=%s",
            msg.update_id,
            type(exc).__name__,
        )
        return t(ctx.lang, "failed"), None


def _callback(
    ctx: ToolContext, msg: InboundMessage, query_id: str, channel: Telegram
) -> int:
    try:  # best effort: stops the button spinner; fails on a stale query
        channel.answer_callback(query_id, "")
    except httpx.HTTPError:
        logger.warning("answer_callback_failed update_id=%s", msg.update_id)
    action, _, token = (msg.callback_data or "").partition(":")
    if action in ("g", "i"):  # a bare amount: gasto or ingreso
        from assistant.llm.tools import execute_kind

        try:
            kind = "gasto" if action == "g" else "ingreso"
            _send_record(ctx, channel, msg, execute_kind(ctx, token, kind))
        except Exception as exc:
            logger.error(
                "pending_failed update_id=%s error=%s",
                msg.update_id,
                type(exc).__name__,
            )
            _send(channel, msg, t(ctx.lang, "failed"))
        return ACK
    if action == "ok":
        from assistant.llm.tools import execute_pending

        try:
            reply = execute_pending(ctx, token)
        except Exception as exc:
            logger.error(
                "pending_failed update_id=%s error=%s",
                msg.update_id,
                type(exc).__name__,
            )
            reply = t(ctx.lang, "failed")
        _send_record(ctx, channel, msg, reply)
    elif action == "no":
        state.pop_pending(msg.chat_id, token)
        _send(channel, msg, t(ctx.lang, "cancelled"))
    elif action == "mo" and token in CURRENCIES:  # /moneda and onboarding buttons
        _send(channel, msg, _set_currency(ctx, msg, token))
    elif action in ("ml", "sp", "pp"):  # photo buttons
        _send(channel, msg, *_photo_button(ctx, msg, action, token))
    elif action == "cal":  # /calendario buttons
        _send(channel, msg, *_calendar(ctx, msg, token), remember=_calendar_note(token))
    elif action == "rs":  # /reset buttons
        confirmed = msg.callback_data == RESET_BUTTONS[0]
        reply = _reset(ctx, msg, channel) if confirmed else t(ctx.lang, "cancelled")
        _send(channel, msg, reply)
    elif action in ("ap", "rj") and ctx.role == "owner":  # access request buttons
        _send(channel, msg, _answer_request(channel, action, token))
    elif action == "rv":  # /usuarios revoke button
        ok = ctx.role == "owner" and state.revoke(token)
        logger.info("user_revoked update_id=%s ok=%s", msg.update_id, ok)
        _send(channel, msg, "✓ Acceso revocado." if ok else "No se pudo revocar.")
    return ACK
