"""Jobs. Cloud Scheduler publishes ``tick`` every hour (UTC); each user gets, in
their own time zone, the digest at 07:00 (reminders and the day's agenda, only
when there is any) and on Sunday at 18:00 the weekly spending summary, with a
button to stop it (``users.resumen_semanal``). No daily spending report. Once a
day, at 12:00 UTC, the tick exports the ledger CSV, applies the retention rules
(``_retention``) and on Sunday also runs the backup. ``digest``, ``checkin`` and
``weekly`` stay runnable by name for manual use.

The assistant is concise: a job messages a chat only when there is something to
say. One failing chat never stops the others. Amounts are in the user's
currency (``users.moneda``), converted from the USD ledger.
"""

from __future__ import annotations

import calendar as cal
import importlib
import logging
from collections.abc import Callable
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from assistant.channels.telegram import Telegram
from assistant.config import get_worker_settings
from assistant.context import ToolContext
from assistant.i18n import t
from assistant.jobs import backup
from assistant.services import agenda, budgets, ledger

log = logging.getLogger(__name__)


def _digest(ctx: ToolContext) -> str | None:
    agenda.enqueue_reminders(ctx)
    return "\n".join(agenda.agenda_lines(ctx, "hoy")) or None


def _checkin(ctx: ToolContext) -> str | None:
    """22:00: the day's spend; the detail lives in the Visor de gastos."""
    entries = ledger.of_day(ctx.chat_id, ledger.today(ctx))
    if not entries:
        return t(ctx.lang, "no_spending")
    expenses = [d for d in entries if d["tipo_mov"] == "gasto"]
    total = sum(
        (ledger.in_currency(d, ctx.currency) for d in expenses), Decimal("0.00")
    )
    return t(ctx.lang, "spent_today", total=total, currency=ctx.currency)


def _weekly(ctx: ToolContext) -> str | None:
    """Sunday 22:00, after the checkin: the week vs income, minus 20% saved."""
    day = ledger.today(ctx)
    since, until = ledger.date_range("semana", day)
    currency = ctx.currency
    expenses = ledger.spend_by_category(ctx.chat_id, since, until, currency)
    total = sum(expenses.values(), Decimal("0.00"))
    month_start = day.replace(day=1)
    income = ledger.total_income(ctx.chat_id, month_start, day, currency)
    if not total and not income:
        return None
    lang = ctx.lang
    lines = [
        t(
            lang,
            "week",
            since=f"{since:%d/%m}",
            until=f"{until:%d/%m}",
            total=total,
            currency=currency,
        )
    ]
    top = sorted((kv for kv in expenses.items() if kv[1] > 0), key=lambda kv: -kv[1])
    if top:
        lines.append(
            t(lang, "top")
            + " · ".join(f"{ledger.display_label(c, lang)} {v}" for c, v in top[:3])
        )
    if income <= 0:
        lines.append(t(lang, "no_income"))
        return "\n".join(lines)
    month = ledger.spend_by_category(ctx.chat_id, month_start, day, currency)
    spent = sum(month.values(), Decimal("0.00"))
    savings = ledger.q(income * Decimal("0.20"))
    left = ledger.q(income - savings - spent)
    days = cal.monthrange(day.year, day.month)[1] - day.day
    weeks = max(Decimal(days) / 7, Decimal(1))
    lines.append(t(lang, "month", income=income, expenses=spent, currency=currency))
    if left >= 0:
        weekly_left = ledger.q(left / weeks)
        lines.append(
            t(
                lang,
                "save",
                savings=savings,
                left=left,
                week=weekly_left,
                currency=currency,
            )
        )
    else:
        lines.append(
            t(lang, "overspent", excess=-left, savings=savings, currency=currency)
        )
    week = Decimal(7) / cal.monthrange(day.year, day.month)[1]
    excess = budgets.excess_line(ctx, expenses, week)
    if excess and excess.startswith("Exceso"):
        lines.append(excess)
    return "\n".join(lines)


JOBS: dict[str, Callable[[ToolContext], str | None]] = {
    "digest": _digest,
    "checkin": _checkin,
    "weekly": _weekly,
}


WEEKLY_HOUR = 18  # Sunday, local time
Keyboard = list[list[tuple[str, str]]] | None


def _tick(ctx: ToolContext, weekly: bool) -> tuple[str | None, Keyboard]:
    """The message due at the user's local hour and its buttons, or None
    (ledger left unread).

    ponytail: :30/:45 offsets (India, Nepal) get the local hour the tick lands
    in (07:30, 18:30); add half-hour ticks if those users want the exact time.
    """
    agenda.sync_gcal(ctx)  # Google-side moves first, so the digest sees them
    if ctx.now.hour == 7:
        return _digest(ctx), None
    if not (weekly and ctx.now.weekday() == 6 and ctx.now.hour == WEEKLY_HOUR):
        return None, None
    if not (text := _weekly(ctx)):
        return None, None
    stop = [[(t(ctx.lang, "weekly_off_button"), "ws:off")]]
    return f"{text}\n\n{t(ctx.lang, 'hint')}", stop


def _ctx(
    chat_id: str, user: dict[str, Any], default_tz: str, now: datetime
) -> ToolContext:
    tz = user.get("zona_horaria") or default_tz
    return ToolContext(
        chat_id=chat_id,
        role=user.get("rol", "beta"),
        currency=user.get("moneda", "USD"),
        timezone=tz,
        update_id=0,
        now=now.astimezone(ZoneInfo(tz)),
        lang=user.get("idioma", "es"),
    )


def _once(state: Any, key: str, fn: Callable[[], object]) -> None:
    """Run a global side effect once per key; a failure leaves the key unset,
    so the next hourly tick retries it. Never blocks the users' messages."""
    if state.cron_done(key):
        return
    try:
        fn()
    except Exception as e:
        log.error(
            "cron_failed job=%s error=%s", key.partition(":")[0], type(e).__name__
        )
        return
    state.mark_cron(key)


def _retention(state: Any, telegram: Telegram, today: date) -> None:
    """Erase revoked chats once their wait is over, and betas silent for
    INACTIVE_DAYS (warned INACTIVE_WARN_DAYS in). A user without ``ultimo_uso``
    starts counting today. The owner is never touched."""
    for chat_id in state.due_purges():
        if state.get_user(chat_id):  # let in again before the wait ended
            state.cancel_purge(chat_id)
        else:
            state.purge_user(chat_id)
            log.info("purged reason=revoked")
    for chat_id, user in state.all_users():
        if user.get("rol") == "owner":
            continue
        try:
            if not (seen := user.get("ultimo_uso")):
                state.mark_seen(chat_id, today.isoformat())
                continue
            idle = (today - date.fromisoformat(seen)).days
            if idle >= state.INACTIVE_DAYS:
                state.purge_user(chat_id)
                log.info("purged reason=inactive")
            elif idle == state.INACTIVE_WARN_DAYS:
                days = state.INACTIVE_DAYS - idle
                lang = user.get("idioma", "es")
                telegram.send_message(chat_id, t(lang, "inactive_warning", days=days))
        except Exception as e:  # one chat never blocks the rest
            log.warning("retention_failed error=%s", type(e).__name__)


def run_job(name: str) -> None:
    if name != "tick" and name not in JOBS:
        raise ValueError(f"unknown job: {name}")
    settings = get_worker_settings()
    now = datetime.now(UTC)
    state = importlib.import_module("assistant.services.state")
    telegram = Telegram(settings.telegram_bot_token)
    if name == "tick" and now.hour >= 12:
        # From 12:00 UTC on, until each one succeeds once (export and retention
        # daily, backup on Sundays): a failure or a missed tick is retried an
        # hour later. Export first, so a purged chat's last day is exported.
        _once(state, f"export:{now:%Y-%m-%d}", lambda: backup.export_ledger(settings))
        _once(
            state,
            f"retention:{now:%Y-%m-%d}",
            lambda: _retention(state, telegram, now.date()),
        )
        if now.weekday() == 6:
            week = now.isocalendar()
            _once(
                state,
                f"backup:{week.year}-W{week.week}",
                lambda: backup.run(settings),
            )
    if name == "weekly":
        backup.run(settings)  # manual run: a failure raises
    if name == "digest":
        _once(state, f"export:{now:%Y-%m-%d}", lambda: backup.export_ledger(settings))
    sent = failed = 0
    for chat_id in state.list_chat_ids():
        try:
            user = state.get_user(chat_id)
            if not user:
                continue
            ctx = _ctx(chat_id, user, settings.default_timezone, now)
            keyboard: Keyboard = None
            if name == "tick":
                weekly = user.get("resumen_semanal", True)
                text, keyboard = _tick(ctx, weekly)
            else:
                text = JOBS[name](ctx)
            if text:
                telegram.send_message(chat_id, text, keyboard)
                sent += 1
        except Exception as e:  # one chat never blocks the rest
            failed += 1
            log.warning("job_chat_failed job=%s error=%s", name, type(e).__name__)
    log.info("job_done job=%s sent=%d failed=%d", name, sent, failed)
