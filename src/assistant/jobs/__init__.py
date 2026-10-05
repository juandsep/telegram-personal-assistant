"""Jobs. Cloud Scheduler publishes ``tick`` every hour (UTC); each user gets, in
their own time zone, the digest at 07:00 (reminders, agenda, yesterday's spend),
the checkin at 22:00 (the day's list) and on Sunday at 22:00 the checkin plus
the weekly summary in one message. Once a day, at 12:00 UTC, the tick exports
the ledger CSV, and on Sunday also runs the backup. ``digest``, ``checkin`` and
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
from datetime import UTC, datetime, timedelta
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
    lines = agenda.agenda_lines(ctx, "hoy")
    yesterday = ledger.today(ctx) - timedelta(days=1)
    expenses = ledger.spend_by_category(ctx.chat_id, yesterday, yesterday, ctx.currency)
    if spent := sum(expenses.values()):
        lines.append(t(ctx.lang, "yesterday", total=spent, currency=ctx.currency))
    return "\n".join(lines) or None


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


def _tick(ctx: ToolContext) -> str | None:
    """The message due at the user's local hour, or None (ledger left unread).

    ponytail: :30/:45 offsets (India, Nepal) get the local hour the tick lands
    in (07:30, 22:30); add half-hour ticks if those users want the exact time.
    """
    if ctx.now.hour == 7:
        return _digest(ctx)
    if ctx.now.hour != 22:
        return None
    parts = [_checkin(ctx)]
    if ctx.now.weekday() == 6:  # Sunday: one message, not two
        parts.append(_weekly(ctx))
    return "\n\n".join([*(p for p in parts if p), t(ctx.lang, "hint")])


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


def run_job(name: str) -> None:
    if name != "tick" and name not in JOBS:
        raise ValueError(f"unknown job: {name}")
    settings = get_worker_settings()
    now = datetime.now(UTC)
    state = importlib.import_module("assistant.services.state")
    if name == "tick" and now.hour >= 12:
        # From 12:00 UTC on, until each one succeeds once (export daily, backup
        # on Sundays): a failure or a missed tick is retried an hour later.
        _once(state, f"export:{now:%Y-%m-%d}", lambda: backup.export_ledger(settings))
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
    telegram = Telegram(settings.telegram_bot_token)
    sent = failed = 0
    for chat_id in state.list_chat_ids():
        try:
            user = state.get_user(chat_id)
            if not user:
                continue
            ctx = _ctx(chat_id, user, settings.default_timezone, now)
            if name == "tick":
                text = _tick(ctx)
            else:
                text = JOBS[name](ctx)
            if text:
                telegram.send_message(chat_id, text)
                sent += 1
        except Exception as e:  # one chat never blocks the rest
            failed += 1
            log.warning("job_chat_failed job=%s error=%s", name, type(e).__name__)
    log.info("job_done job=%s sent=%d failed=%d", name, sent, failed)
