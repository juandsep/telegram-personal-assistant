"""Webhook entrypoint (assistant-api).

Verifies the secret token and the secret route before parsing, checks the
allowlist, deduplicates by update_id and publishes to Pub/Sub. Returns 2xx fast;
never calls the LLM. The only state it writes is the dedup marker and, for
``/start <code>`` from an unknown chat, the invite redemption.

Also serves each chat's agenda as a private ICS feed at ``/ics/{token}.ics``
(read-only; the token is the only secret, so it is never logged), and a
month's ledger as a Telegram Mini App at ``/visor``: the page posts Telegram's
signed initData to ``/visor/datos``, checked with Telegram's Ed25519 public key
(no bot token here, no secret in the URL).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import re
import time
from datetime import UTC, date, datetime
from typing import Any
from urllib.parse import parse_qsl
from zoneinfo import ZoneInfo

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from fastapi import FastAPI, Request, Response
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import HTMLResponse, JSONResponse

from assistant.channels.telegram import parse_update
from assistant.config import get_api_settings
from assistant.services import agenda, pubsub, state, tablero

logger = logging.getLogger(__name__)
app = FastAPI(title="assistant-api")
_MES = re.compile(r"(20\d\d)-(0[1-9]|1[0-2])")
# Telegram's production key for third-party initData (core.telegram.org/bots/webapps)
TG_PUBLIC_KEY = Ed25519PublicKey.from_public_bytes(
    bytes.fromhex("e7bf03a2fa4602af4580703d88dda5bb59f32ed8b02a56c187fe7d34caed242d")  # noqa: E501 # pragma: allowlist secret
)
INIT_DATA_MAX_AGE = 24 * 3600  # seconds; Telegram signs at each Mini App launch
VISOR_JS = """const tg = window.Telegram.WebApp;
async function cargar(mes) {
  const r = await fetch("/visor/datos" + (mes ? "?mes=" + mes : ""), {
    method: "POST", headers: {Authorization: "tma " + tg.initData}});
  if (r.ok) document.documentElement.innerHTML = await r.text();
  else document.body.textContent = "Telegram → Visor de gastos / Expense viewer";
}
document.addEventListener("click", (e) => {
  const a = e.target.closest("a[href^='?mes=']");
  if (a) { e.preventDefault(); cargar(a.getAttribute("href").slice(5)); }
});
tg.ready();
cargar("");
"""
VISOR = f"""<!doctype html>
<html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Visor de gastos</title>
<script src="https://telegram.org/js/telegram-web-app.js"></script>
</head><body><script>{VISOR_JS}</script></body></html>
"""
_JS_HASH = base64.b64encode(hashlib.sha256(VISOR_JS.encode()).digest()).decode()
DASH_HEADERS = {
    "Cache-Control": "no-store",
    "Referrer-Policy": "no-referrer",
    "X-Robots-Tag": "noindex",
    "Content-Security-Policy": (
        f"default-src 'none'; script-src https://telegram.org 'sha256-{_JS_HASH}'; "
        "connect-src 'self'; style-src 'unsafe-inline'"
    ),
}


def init_data_chat(init_data: str, bot_id: str, now: float) -> str | None:
    """The chat_id (= user id in a private chat) of fresh, Telegram-signed
    Mini App initData; None if unsigned, tampered, stale or malformed."""
    campos = dict(parse_qsl(init_data, keep_blank_values=True))
    firma = campos.pop("signature", "")
    campos.pop("hash", None)
    check = f"{bot_id}:WebAppData\n" + "\n".join(
        f"{k}={v}" for k, v in sorted(campos.items())
    )
    try:
        TG_PUBLIC_KEY.verify(
            base64.urlsafe_b64decode(firma + "=" * (-len(firma) % 4)), check.encode()
        )
        if now - int(campos["auth_date"]) > INIT_DATA_MAX_AGE:
            return None
        return str(json.loads(campos["user"])["id"])
    except (InvalidSignature, ValueError, KeyError, TypeError):
        return None


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/ics/{token}.ics")
def ics_feed(token: str) -> Response:
    chat_id = state.chat_for_ics_token(token)  # checks the format first
    if chat_id is None:
        logger.info("ics status=404")
        return Response(status_code=404)
    body = agenda.ics(chat_id, datetime.now(UTC))
    logger.info("ics status=200")
    return Response(
        body,
        media_type="text/calendar; charset=utf-8",
        headers={"Cache-Control": "private, max-age=300"},
    )


@app.get("/visor")
def visor() -> Response:
    return HTMLResponse(VISOR, headers=DASH_HEADERS)


@app.post("/visor/datos")
def visor_datos(request: Request, mes: str | None = None) -> Response:
    init_data = request.headers.get("Authorization", "").removeprefix("tma ")
    bot_id = get_api_settings().telegram_bot_id
    chat_id = init_data_chat(init_data, bot_id, time.time()) if bot_id else None
    user = state.get_user(chat_id) if chat_id else None
    if user is None:  # unsigned, stale, or not (any longer) a user
        logger.info("visor status=403")
        return Response(status_code=403, headers=DASH_HEADERS)
    if mes is None:
        zona = user.get("zona_horaria") or "America/Panama"
        dia = datetime.now(ZoneInfo(zona)).date()
    elif match := _MES.fullmatch(mes):
        dia = date(int(match[1]), int(match[2]), 1)
    else:
        logger.info("visor status=400")
        return Response(status_code=400, headers=DASH_HEADERS)
    body = tablero.render(str(chat_id), dia, user.get("idioma", "es"))
    logger.info("visor status=200")
    return HTMLResponse(body, headers=DASH_HEADERS)


@app.post("/tg/{path}")
async def webhook(path: str, request: Request) -> Response:
    settings = get_api_settings()

    # 1. Constant-time checks before parsing the body. Telegram does not sign
    # the webhook, so both the header and the route are secrets.
    provided = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
    if not hmac.compare_digest(provided, settings.webhook_secret_token):
        return Response(status_code=403)
    if not hmac.compare_digest(path, settings.webhook_path):
        return Response(status_code=403)

    # 2. Parse; anything we do not handle is acknowledged and dropped.
    try:
        update = json.loads(await request.body())
    except ValueError:
        return Response(status_code=200)
    return await run_in_threadpool(_accept, update, settings.updates_topic)


def _start_code(text: str) -> str:
    cmd, _, code = text.strip().partition(" ")
    return code.strip() if cmd == "/start" else ""


def _accept(update: Any, topic: str) -> Response:
    msg = parse_update(update)
    if msg is None:
        return Response(status_code=200)

    # 3. Allowlist. The one exception: /start <code> redeems an invite. A
    #    stranger is dropped here without spending tokens.
    if state.get_user(msg.chat_id) is None:
        code = _start_code(msg.text)
        if not code or not state.redeem_invite(code, msg.chat_id):
            logger.info("dropped update_id=%s reason=unknown_chat", msg.update_id)
            return Response(status_code=200)
        logger.info("invite_redeemed update_id=%s", msg.update_id)

    # 4. Dedup (Telegram retries on non-2xx), then hand off to the worker.
    if not state.mark_processed(msg.update_id):
        return Response(status_code=200)
    try:
        pubsub.publish(topic, update)
    except Exception as exc:
        # Let Telegram retry instead of losing the message.
        logger.error(
            "publish_failed update_id=%s error=%s", msg.update_id, type(exc).__name__
        )
        state.unmark_processed(msg.update_id)
        return Response(status_code=500)
    if msg.text and not msg.callback_query_id:
        # Telegram runs a method returned in the webhook reply: "escribiendo…"
        # shows at once while the worker (maybe cold) and the LLM answer.
        typing = {
            "method": "sendChatAction",
            "chat_id": msg.chat_id,
            "action": "typing",
        }
        return JSONResponse(typing)
    return Response(status_code=200)
