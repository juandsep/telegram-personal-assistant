"""Budget advice: pure rules over the ledger, no LLM.

A per-category budget from ``preferences/{chat_id}`` wins; without one, the
50/30/20 rule over the month's income caps ``necesidades`` and ``ocio``.
Budget caps are stored in USD; spend, income and caps are compared and
shown in the user's currency (caps at today's rate).
"""

from __future__ import annotations

import calendar as cal
import importlib
from collections.abc import Mapping
from decimal import Decimal

from assistant.context import BUCKET_OF, ToolContext
from assistant.i18n import t
from assistant.services import ledger

# 50/30/20: ahorro (20%) is a floor, not a cap, so saving more is never an excess.
CAPS = {"necesidades": Decimal("0.50"), "ocio": Decimal("0.30")}


def largest_excess(
    expenses: Mapping[str, Decimal],
    budget: Mapping[str, str] | None,
    income: Decimal,
    factor: Decimal = Decimal(1),
) -> tuple[str, Decimal, Decimal] | None:
    """Key with the largest spend over its cap, as ``(key, spent, cap)``.

    Keys are categories when ``presupuesto`` is set, else 50/30/20 buckets.
    ``factor`` pro-rates monthly caps (e.g. 7/30 for a week). None if no excess.
    """
    if budget:
        spend = dict(expenses)
        caps = {k: Decimal(v) for k, v in budget.items()}
    else:
        spend = {}
        for cat, amount in expenses.items():
            bucket = BUCKET_OF.get(cat, "ocio")
            spend[bucket] = spend.get(bucket, Decimal(0)) + amount
        caps = {b: income * pct for b, pct in CAPS.items()}
    worst = max(
        (
            (k, spend.get(k, Decimal(0)), ledger.q(cap * factor))
            for k, cap in caps.items()
        ),
        key=lambda t: t[1] - t[2],
        default=None,
    )
    return worst if worst is not None and worst[1] > worst[2] else None


def excess_line(
    ctx: ToolContext, expenses: Mapping[str, Decimal], factor: Decimal
) -> str | None:
    """One line on the largest excess; None when there is nothing to compare to."""
    day = ledger.today(ctx)
    prefs = importlib.import_module("assistant.services.state").get_preferences(
        ctx.chat_id
    )
    budget = (prefs or {}).get("presupuesto")
    if budget and ctx.currency != "USD":
        rate = importlib.import_module("assistant.services.fx").rate(ctx.currency, day)[
            0
        ]
        budget = {k: str(Decimal(v) * rate) for k, v in budget.items()}
    income = ledger.total_income(ctx.chat_id, day.replace(day=1), day, ctx.currency)
    if not budget and income <= 0:
        return None
    excess = largest_excess(expenses, budget, income, factor)
    if excess is None:
        return t(ctx.lang, "within_budget")
    key, spent, cap = excess
    rule = "" if budget else " (50/30/20)"
    cat = ledger.display_label(key, ctx.lang)
    extra = spent - cap
    return t(
        ctx.lang,
        "over_budget",
        cat=cat,
        rule=rule,
        spent=spent,
        cap=cap,
        extra=extra,
        currency=ctx.currency,
    )


def recommend_budget(ctx: ToolContext, period: str = "mes") -> str:
    day = ledger.today(ctx)
    since, until = ledger.date_range(period, day)
    expenses = ledger.spend_by_category(ctx.chat_id, since, until, ctx.currency)
    days_in_month = cal.monthrange(day.year, day.month)[1]
    factor = (
        Decimal(1)
        if period == "mes"
        else Decimal((until - since).days + 1) / days_in_month
    )
    line = excess_line(ctx, expenses, factor)
    return line or t(ctx.lang, "no_budget")
