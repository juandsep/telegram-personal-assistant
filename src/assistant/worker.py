"""Worker entrypoint (assistant-worker).

Push subscriber for assistant-updates (user messages) and assistant-cron
(scheduled jobs), and target of the Cloud Tasks reminders. The service is
private: Cloud Run validates the OIDC token (Pub/Sub, Cloud Tasks) before a
request reaches these routes, so no unauthenticated caller gets here.

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
from datetime import datetime
from functools import cache
from typing import Any
from zoneinfo import ZoneInfo

import httpx
from fastapi import FastAPI, Request, Response
from fastapi.concurrency import run_in_threadpool

from assistant.channels.base import InboundMessage
from assistant.channels.telegram import Telegram, parse_update
from assistant.config import WorkerSettings, get_worker_settings
from assistant.context import ToolContext
from assistant.i18n import idioma, t
from assistant.services import agenda, quick, state

logger = logging.getLogger(__name__)
app = FastAPI(title="assistant-worker")

ACK = 204
GIF_USAGE = (
    "Envía un GIF con el texto gasto, gasto restaurantes, ingreso o ingreso "
    "salario (sin clave va a general), o responde a uno con /gif gasto "
    "restaurantes. /gif borrar respondiendo a un GIF lo quita."
)
GIF_OWNER_ONLY = "Solo el owner cura los GIFs."
OWNER_COMMANDS = ("/invitar", "/usuarios")
INVITAR_USAGE = "Uso: /invitar <nombre>. Crea un enlace de un uso, válido 24 h."
LEDGER_COMMANDS = ("/ultimos", "/editar", "/anular", "/gif")
REGISTROS = {"registrar_gasto": "gasto", "registrar_ingreso": "ingreso"}


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/push")
async def push(request: Request) -> Response:
    try:
        envelope = json.loads(await request.body())
        payload = json.loads(base64.b64decode(envelope["message"]["data"]))
    except (ValueError, KeyError, TypeError, binascii.Error):
        # Malformed: ack so Pub/Sub does not retry it forever.
        logger.warning("malformed_envelope")
        return Response(status_code=ACK)
    return Response(status_code=await run_in_threadpool(_route, payload))


@app.post("/tasks/reminder")
async def reminder(request: Request) -> Response:
    """Cloud Tasks at the reminder time. Always 2xx unless Firestore fails."""
    try:
        body = json.loads(await request.body())
        chat_id, evento_id = str(body["chat_id"]), str(body["evento_id"])
    except (ValueError, KeyError, TypeError):
        logger.warning("malformed_task")
        return Response(status_code=ACK)
    await run_in_threadpool(_remind, chat_id, evento_id)
    return Response(status_code=ACK)


def _remind(chat_id: str, evento_id: str) -> None:
    texto = agenda.aviso(chat_id, evento_id)
    if texto is None:  # cancelled or missing
        return
    try:
        Telegram(get_worker_settings().telegram_bot_token).send_message(chat_id, texto)
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
    zona = user.get("zona_horaria") or settings.default_timezone
    lang = user.get("idioma", "es")
    if msg.language_code and (nuevo := idioma(msg.language_code)) != lang:
        lang = nuevo
        try:  # best effort: the phone's language, kept for the scheduled jobs
            state.set_idioma(msg.chat_id, lang)
        except Exception as exc:
            logger.warning("idioma_failed error=%s", type(exc).__name__)
    return ToolContext(
        chat_id=msg.chat_id,
        rol=user.get("rol", "beta"),
        moneda=user.get("moneda", "USD"),
        zona_horaria=zona,
        update_id=msg.update_id,
        ahora=datetime.now(ZoneInfo(zona)),
        idioma=lang,
        fun=bool(user.get("fun")),
    )


def handle_update(msg: InboundMessage, settings: WorkerSettings) -> int:
    user = state.get_user(msg.chat_id)
    if user is None:  # removed after the api accepted it
        return ACK
    ctx = _context(user, msg, settings)
    channel = Telegram(settings.telegram_bot_token)
    if msg.callback_query_id:
        return _callback(ctx, msg, msg.callback_query_id, channel)
    if msg.text.startswith("/zona"):
        _send(channel, msg, _zona(ctx, msg))
        return ACK
    if msg.text.startswith(("/start", "/ayuda", "/help")):
        _send(channel, msg, t(ctx.idioma, "welcome"))
        if msg.text.startswith("/start") and settings.api_url:  # pin the Visor
            _tablero(ctx, channel, msg, settings)
        return ACK
    if msg.animation_file_id:
        _send(channel, msg, _gif_command(ctx, msg, msg.caption, msg.animation_file_id))
        return ACK
    if not msg.text.strip():
        _send(channel, msg, t(ctx.idioma, "text_only"))
        return ACK
    if _is_ical_url(msg.text):  # the link sent on its own, after /conectar
        msg = dataclasses.replace(msg, text=f"/conectar {msg.text.strip()}")
    if msg.text.startswith(("/calendario", "/conectar", "/vincular")):
        reply = _command(ctx, msg, settings)
        if msg.text.startswith("/conectar ") and msg.message_id is not None:
            # The message holds the secret iCal URL: drop it from the chat.
            try:
                channel.delete_message(msg.chat_id, msg.message_id)
                reply += "\nBorré tu mensaje con el enlace."
            except httpx.HTTPError:
                logger.warning("delete_failed update_id=%s", msg.update_id)
        _send(channel, msg, reply)
        return ACK
    if msg.text.startswith(OWNER_COMMANDS):
        _send(channel, msg, *_owner_command(ctx, msg, settings))
        return ACK
    if msg.text.startswith("/fun"):
        _send(channel, msg, _fun(ctx, msg))
        return ACK
    if (campos := quick.correccion(msg.text)) is not None:
        if not campos:
            _send(channel, msg, t(ctx.idioma, "corregir_usage"))
            return ACK
        args = {"indice": 1, **campos}  # the last movement
        usage = t(ctx.idioma, "corregir_usage")
        _send(channel, msg, *_tool(ctx, msg, "editar_movimiento", args, usage))
        return ACK
    if msg.text.startswith("/tablero"):
        _tablero(ctx, channel, msg, settings)
        return ACK
    if msg.text.startswith(LEDGER_COMMANDS):
        _send(channel, msg, *_ledger_command(ctx, msg))
        return ACK
    entry = quick.parse(msg.text)
    if entry is not None:  # deterministic: no LLM, no spend, no history
        _quick(ctx, msg, entry, channel)
        return ACK

    # 1. Rate limit and daily cap: fail closed without calling the LLM.
    if not state.check_rate(msg.chat_id, settings.max_msgs_per_minute) or (
        state.llm_spend_today(msg.chat_id) >= settings.max_llm_usd_per_day
    ):
        logger.info("limit_reached update_id=%s", msg.update_id)
        _send(channel, msg, t(ctx.idioma, "limit"))
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
        _send(channel, msg, t(ctx.idioma, "failed"))
        return ACK

    # 3-5. Reply, account, trace.
    registros = [REGISTROS[t] for t in result.tools if t in REGISTROS]
    registro = bool(registros) and not result.keyboard
    reply = result.reply
    if registro and not ctx.fun:
        reply += "\n" + t(ctx.idioma, "corregir")
    _send(channel, msg, reply, result.keyboard)
    if registro and ctx.fun:
        _gif(channel, msg, registros[-1])
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
        importlib.import_module("assistant.services.busy").validar(text)
    except Exception:
        return False
    return True


def _command(ctx: ToolContext, msg: InboundMessage, settings: WorkerSettings) -> str:
    """/calendario [enlace|nuevo], /conectar <url> and /vincular <id|off>."""
    cmd, _, arg = msg.text.strip().partition(" ")
    cmd, arg = cmd.split("@")[0], arg.strip()
    try:
        if cmd == "/conectar":
            if not arg:
                return t(ctx.idioma, "conectar_hint")
            try:
                busy = importlib.import_module("assistant.services.busy")
            except ImportError:
                return t(ctx.idioma, "no_disponible")
            return str(busy.conectar(ctx, arg))
        if cmd == "/vincular":
            gcal = importlib.import_module("assistant.services.gcal")
            if not arg:
                return t(ctx.idioma, "vincular_hint", sa=gcal.SA_EMAIL)
            return str(gcal.vincular(ctx, arg))
        if arg in ("enlace", "nuevo"):
            if not settings.api_url:
                return t(ctx.idioma, "enlace_no_config")
            token = state.ics_token(ctx.chat_id, rotate=arg == "nuevo")
            hint = t(ctx.idioma, "google_hint")
            return f"{settings.api_url}/ics/{token}.ics\n{hint}"
        return agenda.semana(ctx)
    except Exception as exc:
        logger.error(
            "command_failed update_id=%s error=%s", msg.update_id, type(exc).__name__
        )
        return t(ctx.idioma, "failed")


def _quick(
    ctx: ToolContext, msg: InboundMessage, entry: quick.Entry, channel: Telegram
) -> None:
    if entry.error:
        _send(channel, msg, t(ctx.idioma, "positivo"))
        return
    if not entry.tipo:  # a bare amount: ask, register on the button
        from assistant.llm import tools

        try:
            pregunta, teclado = tools.ask_tipo(ctx, entry.monto, entry.moneda)
        except Exception as exc:
            logger.error(
                "quick_failed update_id=%s error=%s", msg.update_id, type(exc).__name__
            )
            _send(channel, msg, t(ctx.idioma, "failed"))
            return
        _send(channel, msg, pregunta, teclado)
        return
    fecha = ctx.ahora.date()
    try:
        ledger = importlib.import_module("assistant.services.ledger")
        if entry.tipo == "ingreso":
            reply = ledger.registrar_ingreso(
                ctx,
                monto=entry.monto,
                moneda=entry.moneda,
                fuente=entry.nota,
                fecha=fecha,
            )
        else:
            item = {
                "monto": entry.monto,
                "categoria": entry.categoria,
                "nota": entry.nota or None,
            }
            reply = ledger.registrar_gasto(
                ctx, items=[item], moneda=entry.moneda, fecha=fecha
            )
    except Exception as exc:
        logger.error(
            "quick_failed update_id=%s error=%s", msg.update_id, type(exc).__name__
        )
        _send(channel, msg, t(ctx.idioma, "failed"))
        return
    logger.info("quick_entry update_id=%s", msg.update_id)
    _registro(ctx, channel, msg, str(reply))


def _registro(
    ctx: ToolContext, channel: Telegram, msg: InboundMessage, reply: str
) -> None:
    """A registration answers with the entry as stored and how to correct it;
    with /fun on, with the reaction GIF only (the text is the fallback when no
    GIF is stored). Anything else (errors such as a missing rate) as is."""
    tipo = {"−": "gasto", "+": "ingreso"}.get(reply[:1])
    if tipo and ctx.fun and _gif(channel, msg, tipo):
        return
    _send(channel, msg, f"{reply}\n{t(ctx.idioma, 'corregir')}" if tipo else reply)


def _fun(ctx: ToolContext, msg: InboundMessage) -> str:
    """/fun toggles GIF replies to registrations."""
    try:
        state.set_fun(ctx.chat_id, not ctx.fun)
    except Exception as exc:
        logger.error(
            "command_failed update_id=%s error=%s", msg.update_id, type(exc).__name__
        )
        return t(ctx.idioma, "failed")
    return t(ctx.idioma, "fun_off" if ctx.fun else "fun_on")


def _zona(ctx: ToolContext, msg: InboundMessage) -> str:
    """/zona America/Bogota: the time zone of the agenda and the reports."""
    zona = msg.text.strip().partition(" ")[2].strip()
    try:
        if not zona or "/" not in zona:
            raise ValueError
        ZoneInfo(zona)
    except (ValueError, KeyError):  # ZoneInfoNotFoundError is a KeyError
        return t(ctx.idioma, "zona_usage", zona=ctx.zona_horaria)
    state.set_zona(ctx.chat_id, zona)
    logger.info("zona_set update_id=%s", msg.update_id)
    return t(ctx.idioma, "zona_ok", zona=zona)


@cache
def _bot_username(bot_token: str) -> str:
    return Telegram(bot_token).username()


def _owner_command(
    ctx: ToolContext, msg: InboundMessage, settings: WorkerSettings
) -> tuple[str, list[list[tuple[str, str]]] | None]:
    """/invitar <nombre> (t.me deep link) and /usuarios (revoke buttons)."""
    if ctx.rol != "owner":
        return state.OWNER_ONLY, None
    cmd, _, nombre = msg.text.strip().partition(" ")
    nombre = nombre.strip()
    if cmd.split("@")[0] == "/invitar":
        if not nombre or len(nombre) > 40:
            return INVITAR_USAGE, None
        code = state.crear_invitacion(nombre)
        logger.info("invite_created update_id=%s", msg.update_id)
        link = f"https://t.me/{_bot_username(settings.telegram_bot_token)}?start={code}"
        return f"Invitación para {nombre} (un uso, 24 h). Reenvíale:\n{link}", None
    filas = state.usuarios()
    texto = "\n".join(f"{u.get('nombre', '?')} ({u.get('rol', '?')})" for _, u in filas)
    botones = [
        [(f"Revocar a {u.get('nombre', '?')}", f"rv:{chat_id}")]
        for chat_id, u in filas
        if u.get("rol") == "beta"
    ]
    return texto or "Sin usuarios.", botones or None


def _ledger_command(
    ctx: ToolContext, msg: InboundMessage
) -> tuple[str, list[list[tuple[str, str]]] | None]:
    """/ultimos, /editar n monto, /anular n (buttons), /gif: no LLM."""

    cmd, _, arg = msg.text.strip().partition(" ")
    cmd, arg = cmd.split("@")[0], arg.strip()
    if cmd == "/gif":
        return _gif_command(ctx, msg, arg, msg.reply_animation_file_id), None
    n, _, rest = arg.partition(" ")
    usage = t(ctx.idioma, "anular_usage" if cmd == "/anular" else "edit_usage")
    args: dict[str, Any] = {"indice": int(n)} if n.isdecimal() else {}
    found = quick.amount(rest) if rest else None
    if cmd == "/ultimos":
        name, args = "ultimos_movimientos", {"n": 5}
    elif cmd == "/editar" and args and found:
        name, args = (
            "editar_movimiento",
            {**args, "monto": found[0], "moneda": found[1]},
        )
    elif cmd == "/anular" and args and not rest:
        name = "anular_movimiento"
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
    except tools.ToolRejected:  # monto <= 0, índice fuera de rango
        return usage, None
    except Exception as exc:
        logger.error(
            "command_failed update_id=%s error=%s", msg.update_id, type(exc).__name__
        )
        return t(ctx.idioma, "failed"), None
    return reply, tools.buttons(token) if token else None


def _tablero(
    ctx: ToolContext, channel: Telegram, msg: InboundMessage, settings: WorkerSettings
) -> None:
    """/tablero: pins the dashboard Mini App (assistant-api /visor) in the chat."""
    if not settings.api_url:
        _send(channel, msg, t(ctx.idioma, "tablero_no_config"))
        return
    try:
        channel.pin_webapp(
            msg.chat_id,
            t(ctx.idioma, "tablero"),
            t(ctx.idioma, "visor"),
            f"{settings.api_url}/visor",
        )
    except httpx.HTTPError:
        logger.warning("pin_failed update_id=%s", msg.update_id)
        _send(channel, msg, t(ctx.idioma, "failed"))


def gif_target(text: str) -> tuple[str, str] | None:
    """``gasto`` -> (gasto, general); ``ingreso salario`` -> (ingreso, salario)."""
    words = text.strip().lower().split()
    if not 1 <= len(words) <= 2 or quick.norm(words[0]) not in state.GIF_TIPOS:
        return None
    clave = words[1] if len(words) == 2 else state.GIF_GENERAL
    return (quick.norm(words[0]), clave) if state.valid_clave(clave) else None


def _gif_command(
    ctx: ToolContext, msg: InboundMessage, arg: str, file_id: str | None
) -> str:
    """Owner-only curation of the shared catalog: add, borrar, list counts."""
    if ctx.rol != "owner":
        return GIF_OWNER_ONLY
    if file_id and arg.strip().lower() == "borrar":
        removed = state.remove_gif(file_id)
        logger.info("gif_removed update_id=%s", msg.update_id)
        return "✓ GIF borrado." if removed else "Ese GIF no está en el catálogo."
    target = gif_target(arg)
    if file_id and target:
        state.add_gif(*target, file_id)
        logger.info("gif_saved update_id=%s", msg.update_id)
        return f"✓ GIF guardado para {target[0]} {target[1]}."
    lines = [GIF_USAGE]
    for tipo in state.GIF_TIPOS:
        counts = ", ".join(
            f"{k} {len(v)}" for k, v in sorted(state.gif_catalog(tipo).items())
        )
        lines.append(f"{tipo}: {counts or 'vacío'}")
    return "\n".join(lines)


def _gif(channel: Telegram, msg: InboundMessage, tipo: str) -> bool:
    """Best effort reaction GIF after a registration; False when none was sent.
    The movement's categoria/fuente picks the GIFs, else ``general``."""
    try:
        ledger = importlib.import_module("assistant.services.ledger")
        clave = ledger.clave(msg.chat_id, msg.update_id, tipo)
        file_id = state.random_gif(tipo, clave)
        if file_id:
            channel.send_animation(msg.chat_id, file_id)
            return True
    except Exception as exc:
        logger.warning(
            "gif_failed update_id=%s error=%s", msg.update_id, type(exc).__name__
        )
    return False


def _send(
    channel: Telegram, msg: InboundMessage, text: str, keyboard: Any = None
) -> None:
    """Best effort: a Telegram error must not make Pub/Sub rerun a paid turn."""
    try:
        channel.send_message(msg.chat_id, text, keyboard)
    except httpx.HTTPError:
        logger.warning("send_failed update_id=%s", msg.update_id)


def _callback(
    ctx: ToolContext, msg: InboundMessage, query_id: str, channel: Telegram
) -> int:
    try:  # best effort: stops the button spinner; fails on a stale query
        channel.answer_callback(query_id, "")
    except httpx.HTTPError:
        logger.warning("answer_callback_failed update_id=%s", msg.update_id)
    action, _, token = (msg.callback_data or "").partition(":")
    if action in ("g", "i"):  # a bare amount: gasto or ingreso
        from assistant.llm.tools import execute_tipo

        try:
            tipo = "gasto" if action == "g" else "ingreso"
            _registro(ctx, channel, msg, execute_tipo(ctx, token, tipo))
        except Exception as exc:
            logger.error(
                "pending_failed update_id=%s error=%s",
                msg.update_id,
                type(exc).__name__,
            )
            _send(channel, msg, t(ctx.idioma, "failed"))
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
            reply = t(ctx.idioma, "failed")
        _registro(ctx, channel, msg, reply)
    elif action == "no":
        state.pop_pending(msg.chat_id, token)
        _send(channel, msg, t(ctx.idioma, "cancelado"))
    elif action == "rv":  # /usuarios revoke button
        ok = ctx.rol == "owner" and state.revocar(token)
        logger.info("user_revoked update_id=%s ok=%s", msg.update_id, ok)
        _send(channel, msg, "✓ Acceso revocado." if ok else "No se pudo revocar.")
    return ACK
