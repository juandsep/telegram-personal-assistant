"""Web dashboard of one chat's month, rendered server-side as plain HTML.

Served by the assistant service to the ``/visor`` Mini App (see ``api.py``). No
own JS: bars are CSS widths/heights. Every value from the ledger goes through
``html.escape``. Amounts are in the user's currency (``ledger.in_currency``).
"""

from __future__ import annotations

import calendar
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal
from html import escape

from assistant.i18n import t
from assistant.services import ledger


def _label(value: str | None, lang: str) -> str:
    return ledger.display_label(value or "", lang)


SAVINGS_GOAL = Decimal("0.20")  # savings target, same 20% as the weekly job
LATEST_ROWS = 15

CSS = """
:root{--bg:#f6f7f9;--card:#fff;--fg:#1d2330;--muted:#667085;--bar:#3b82f6;
--in:#16a34a;--out:#dc2626;--line:#e4e7ec}
@media (prefers-color-scheme:dark){:root{--bg:#0f1218;--card:#181c24;
--fg:#e6e8ec;--muted:#98a2b3;--bar:#60a5fa;--in:#4ade80;--out:#f87171;
--line:#2a303b}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);
font:15px/1.4 system-ui,-apple-system,"Segoe UI",sans-serif}
main{max-width:720px;margin:0 auto;padding:16px}
h1{font-size:1.3rem;margin:0 0 4px}h2{font-size:1rem;margin:0 0 12px}
nav{display:flex;justify-content:space-between;margin-bottom:16px}
a{color:var(--bar)}
section{background:var(--card);border:1px solid var(--line);border-radius:12px;
padding:16px;margin-bottom:16px}
.kpis{display:grid;grid-template-columns:repeat(2,1fr);gap:12px}
.kpis div{background:var(--card);border:1px solid var(--line);border-radius:12px;
padding:12px}
.kpis small,.muted{color:var(--muted)}.kpis b{display:block;font-size:1.2rem}
.in{color:var(--in)}.out{color:var(--out)}
.row{display:grid;grid-template-columns:7.5rem 1fr 5.5rem;gap:8px;
align-items:center;margin:6px 0}
.row span:first-child{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.track{background:var(--line);border-radius:4px;height:10px}
.fill{background:var(--bar);border-radius:4px;height:10px}
.num{text-align:right;font-variant-numeric:tabular-nums}
.days{display:flex;align-items:flex-end;gap:2px;height:120px}
.days div{flex:1;background:var(--bar);border-radius:2px 2px 0 0;min-height:1px}
.axis{display:flex;justify-content:space-between;color:var(--muted);
font-size:.75rem;margin-top:4px}
ul{list-style:none;margin:0;padding:0}
li{display:flex;justify-content:space-between;gap:8px;padding:8px 0;
border-top:1px solid var(--line)}li:first-child{border-top:0}
@media (min-width:560px){.kpis{grid-template-columns:repeat(4,1fr)}}
"""


def _entry_label(d: dict) -> str | None:
    return d.get("nota") or d.get("categoria") or d.get("fuente")


def _money(value: Decimal) -> str:
    return f"{value:,.2f}"


def _pct(part: Decimal, total: Decimal) -> Decimal:
    """Bar length 0-100 for CSS; never negative."""
    return max(Decimal(0), part) * 100 / total if total > 0 else Decimal(0)


def render(chat_id: str, month: date, lang: str = "es", currency: str = "USD") -> str:
    """The month of ``month`` (any day in it) as a full HTML page in ``lang``,
    amounts in ``currency``."""
    since = month.replace(day=1)
    days = calendar.monthrange(since.year, since.month)[1]
    until = since.replace(day=days)
    entries = ledger.active_entries(chat_id, since, until)

    income = expenses = Decimal("0.00")
    by_category: dict[str, Decimal] = defaultdict(Decimal)
    by_day: dict[int, Decimal] = defaultdict(Decimal)
    for d in entries:
        # ponytail: one fx cache read per foreign-currency row; memo per day if slow
        amount = d["_monto"] = ledger.in_currency(d, currency)
        if d["tipo_mov"] == "ingreso":
            income += amount
        else:
            expenses += amount
            by_category[d.get("categoria") or "otros"] += amount
            by_day[date.fromisoformat(d["fecha"]).day] += amount
    savings = income - expenses
    goal = ledger.q(income * SAVINGS_GOAL)
    if income > 0:
        rate = f"{ledger.q(savings * 100 / income)}%"
        goal_class = "in" if savings >= goal else "out"
        goal_text = t(lang, "d_goal", goal=_money(goal), currency=currency)
    else:
        rate, goal_class, goal_text = "—", "muted", t(lang, "d_no_income")

    cats = sorted(by_category.items(), key=lambda kv: -kv[1])
    top_category = max((v for _, v in cats), default=Decimal(0))
    category_rows = (
        "".join(
            f'<div class="row"><span>{escape(_label(c, lang))}</span>'
            '<div class="track">'
            f'<div class="fill" style="width:{_pct(v, top_category):.1f}%"></div></div>'
            f'<span class="num">{_money(v)}</span></div>'
            for c, v in cats
        )
        or f'<p class="muted">{t(lang, "d_no_expenses")}</p>'
    )

    top_day = max(by_day.values(), default=Decimal(0))
    bars = "".join(
        f'<div style="height:{_pct(by_day[n], top_day):.1f}%" '
        f'title="{n}: {_money(by_day[n])} {currency}"></div>'
        for n in range(1, days + 1)
    )

    recent = sorted(
        entries, key=lambda d: (d["fecha"], str(d.get("creado", ""))), reverse=True
    )[:LATEST_ROWS]
    entry_rows = (
        "".join(
            f"<li><span>{date.fromisoformat(d['fecha']):%d/%m} "
            f"{escape(_label(_entry_label(d), lang))}"
            f'</span><span class="num {"in" if d["tipo_mov"] == "ingreso" else "out"}">'
            f"{'+' if d['tipo_mov'] == 'ingreso' else '−'}"
            f"{_money(abs(d['_monto']))}</span></li>"
            for d in recent
        )
        or f'<li class="muted">{t(lang, "d_no_entries")}</li>'
    )

    title = f"{t(lang, 'months').split()[since.month - 1]} {since.year}"
    heading = t(lang, "d_title", month=title)
    prev_month = (since - timedelta(days=1)).strftime("%Y-%m")
    next_month = (until + timedelta(days=1)).strftime("%Y-%m")
    return f"""<!doctype html>
<html lang="{lang}"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="light dark">
<title>{heading}</title><style>{CSS}</style></head>
<body><main>
<h1>{heading}</h1><p class="muted">{t(lang, "d_amounts_in", currency=currency)}</p>
<nav><a href="?mes={prev_month}">{t(lang, "d_prev")}</a>
<a href="?mes={next_month}">{t(lang, "d_next")}</a></nav>
<div class="kpis">
<div><small>{t(lang, "d_income")}</small><b class="in">{_money(income)}</b></div>
<div><small>{t(lang, "d_expenses")}</small><b class="out">{_money(expenses)}</b></div>
<div><small>{t(lang, "d_savings")}</small><b>{_money(savings)}</b></div>
<div><small>{t(lang, "d_rate")}</small><b class="{goal_class}">{rate}</b>
<small>{goal_text}</small></div>
</div>
<section><h2>{t(lang, "d_by_category")}</h2>{category_rows}</section>
<section><h2>{t(lang, "d_daily")}</h2><div class="days">{bars}</div>
<div class="axis"><span>1</span><span>{days}</span></div></section>
<section><h2>{t(lang, "d_latest", n=LATEST_ROWS)}</h2><ul>{entry_rows}</ul></section>
</main></body></html>
"""
