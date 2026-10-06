"""Finance ledger on Firestore: append-only, every amount stored in USD.

Users see amounts in their own ``users.moneda`` (``in_currency``): the original
amount when it was typed in that currency, else the USD amount at the
movement day's rate. Storage never changes.

Layout: ``ledger/{chat_id}/movimientos/{doc_id}`` (movimientos = entries).
Stored field names are Spanish; the code maps them at this boundary:

- ``fecha``: day (ISO date); ``monto``: amount in USD (str, 0.01);
  ``moneda``: currency ("USD");
- ``monto_original``/``moneda_original``: the amount and currency as typed;
  ``tasa``: rate (moneda_original per 1 USD); ``fuente_tasa``: rate source
  (usd|trm|ecb) from ``services.fx``;
- ``categoria``: category (gasto) or ``fuente``: source (ingreso);
- ``tipo_mov``: entry kind, gasto (expense) | ingreso (income); ``nota``: note;
- ``tipo``: row kind, registro (record) | reverso (reversal); ``reversa``
  (reverso only): the registro doc id it cancels;
- ``batch_id``, ``update_id``, ``creado`` (created, server timestamp).

Rows written before the USD ledger lack the ``*_original``/``tasa`` fields.

Doc ids: gasto ``{update_id}-{i}``, ingreso ``{update_id}-i0``, undo reverso
``{batch_id}-r{i}``, edit/void reverso ``{registro_id}-x`` and edit's new
registro ``{update_id}-e0`` (batch ``e{update_id}``). Every call creates its
docs with ``create()`` in one atomic batch, so a Pub/Sub retry of the same
update hits AlreadyExists and writes nothing. Nothing is ever edited or deleted.

Reads query one chat's subcollection by a single field (``fecha``, ``creado``,
``batch_id`` or ``update_id``): automatic single-field indexes, no composite
index. Sums run in Python with Decimal. Doc paths contain chat_ids: never log
them.
"""

from __future__ import annotations

import importlib
import logging
import os
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from functools import cache
from typing import Any
from zoneinfo import ZoneInfo

from google.api_core.exceptions import Conflict
from google.cloud import firestore
from google.cloud.firestore import FieldFilter

from assistant.context import ToolContext
from assistant.i18n import category_name, t

log = logging.getLogger(__name__)

CENT = Decimal("0.01")


@cache
def _db() -> firestore.Client:
    return firestore.Client(
        project=os.environ.get("GCP_PROJECT_ID") or None,
        database=os.environ.get("FIRESTORE_DATABASE") or None,  # staging has its own
    )


def _state() -> Any:
    return importlib.import_module("assistant.services.state")


def _col(chat_id: str) -> Any:
    return _db().collection("ledger").document(chat_id).collection("movimientos")


def q(value: object) -> Decimal:
    """Amount as Decimal rounded to cents; str() first so floats never leak."""
    return Decimal(str(value)).quantize(CENT, rounding=ROUND_HALF_UP)


def today(ctx: ToolContext) -> date:
    return ctx.now.astimezone(ZoneInfo(ctx.timezone)).date()


def date_range(period: str, day: date) -> tuple[date, date]:
    """Inclusive date range for hoy|semana|mes ending on ``day``."""
    if period == "hoy":
        return day, day
    if period == "semana":
        return day - timedelta(days=day.weekday()), day
    if period == "mes":
        return day.replace(day=1), day
    raise ValueError("periodo")


def _create(chat_id: str, docs: dict[str, dict]) -> bool:
    """Create all docs atomically. False when they already exist (a retry)."""
    col = _col(chat_id)
    batch = _db().batch()
    for doc_id, data in docs.items():
        batch.create(
            col.document(doc_id), {**data, "creado": firestore.SERVER_TIMESTAMP}
        )
    try:
        batch.commit()
    except Conflict:
        log.info("ledger_retry docs=%d", len(docs))
        return False
    log.info("ledger_write docs=%d", len(docs))
    return True


def query_entries(chat_id: str, field: str, since: Any, until: Any) -> list[dict]:
    """Docs of one chat with ``since <= field < until``."""
    query = (
        _col(chat_id)
        .where(filter=FieldFilter(field, ">=", since))
        .where(filter=FieldFilter(field, "<", until))
    )
    return [s.to_dict() for s in query.stream()]


def _by_date(chat_id: str, kind: str, since: date, until: date) -> list[dict]:
    end = (until + timedelta(days=1)).isoformat()
    docs = query_entries(chat_id, "fecha", since.isoformat(), end)
    return [d for d in docs if d["tipo_mov"] == kind]


def _fx(amount: object, currency: str, day: date, lang: str = "es") -> dict | str:
    """USD fields for one amount, or the reply when the rate is unavailable."""
    original = q(amount)
    if original <= 0:
        return t(lang, "positive")
    cur = currency.strip().upper()
    fx = importlib.import_module("assistant.services.fx")
    try:
        usd, rate, source = fx.to_usd(original, cur, day)
    except fx.FxError as e:
        if str(e) == "unsupported":
            return t(lang, "currency_unsupported")
        return t(lang, "no_rate", cur=cur)
    return {
        "monto": str(usd),
        "moneda": "USD",
        "monto_original": str(original),
        "moneda_original": cur,
        "tasa": str(rate),
        "fuente_tasa": source,
    }


def _figure(value: Decimal) -> str:
    """2000 -> "2,000"; 12.5 -> "12.50"."""
    value = abs(value)
    return f"{value:,.0f}" if value == value.to_integral() else f"{value:,.2f}"


def display_label(value: str, lang: str = "es") -> str:
    """ "supermercado" -> "Mercado" (or Groceries, 超市), "pan" -> "Pan": display."""
    return category_name(lang, value) or value[:1].upper() + value[1:]


def in_currency(d: dict, base: str) -> Decimal:
    """A movement's amount in ``base``: exact when typed in it, else its USD at
    the movement day's rate. Keeps the sign, so reversos net out in sums."""
    if d.get("moneda_original", "USD") == base:
        return q(d.get("monto_original", d["monto"]))
    if base == "USD":
        return q(d["monto"])
    fx = importlib.import_module("assistant.services.fx")
    rate = fx.rate(base, date.fromisoformat(d["fecha"]))[0]
    return q(q(d["monto"]) * rate)


def describe(d: dict, sep: str = " · ", lang: str = "es", base: str = "USD") -> str:
    """One movement as "−0.49 USD · café (2,000 COP)"; a reverso as its registro."""
    sign = "−" if d["tipo_mov"] == "gasto" else "+"
    fx = importlib.import_module("assistant.services.fx")
    try:
        amount = in_currency(d, base)
    except fx.FxError:  # rate unavailable: the stored USD, never a failed reply
        amount, base = q(d["monto"]), "USD"
    text = f"{sign}{abs(amount)} {base}"
    label = d.get("nota") or d.get("categoria") or d.get("fuente")
    if label:
        text += f"{sep}{display_label(label, lang)}"
    currency = str(d.get("moneda_original", "USD")).upper()
    if currency != base:
        text += f" ({_figure(Decimal(d.get('monto_original', d['monto'])))} {currency})"
    return text


# ponytail: batch_id = update_id, so one record_expense call per turn (the prompt
# batches items); a second call in the same turn is treated as a retry.
def record_expense(
    ctx: ToolContext, items: list[dict], currency: str, day: date
) -> str:
    batch = f"g{ctx.update_id}"
    docs = {}
    for i, item in enumerate(items):
        usd = _fx(item["amount"], currency, day, ctx.lang)
        if isinstance(usd, str):
            return usd
        docs[f"{ctx.update_id}-{i}"] = {
            "fecha": day.isoformat(),
            **usd,
            "categoria": str(item.get("category") or "").strip() or "otros",
            "tipo_mov": "gasto",
            "nota": str(item.get("note") or ""),
            "batch_id": batch,
            "update_id": ctx.update_id,
            "tipo": "registro",
        }
    _create(ctx.chat_id, docs)
    _state().set_last_batch(ctx.chat_id, batch)
    return "; ".join(_with_category(d, ctx.lang, ctx.currency) for d in docs.values())


def _with_category(d: dict, lang: str, base: str = "USD") -> str:
    """ "−12.00 USD · Lunch · Restaurants": the category even when a note shows."""
    line = describe(d, lang=lang, base=base)
    cat = d.get("categoria")
    return f"{line} · {display_label(cat, lang)}" if cat and d.get("nota") else line


def record_income(
    ctx: ToolContext,
    amount: Decimal,
    currency: str,
    source: str,
    day: date,
    note: str | None = None,
) -> str:
    usd = _fx(amount, currency, day, ctx.lang)
    if isinstance(usd, str):
        return usd
    batch = f"i{ctx.update_id}"
    doc = {
        "fecha": day.isoformat(),
        **usd,
        "fuente": source or "",
        "tipo_mov": "ingreso",
        "nota": note or "",
        "batch_id": batch,
        "update_id": ctx.update_id,
        "tipo": "registro",
    }
    _create(ctx.chat_id, {f"{ctx.update_id}-i0": doc})
    _state().set_last_batch(ctx.chat_id, batch)
    return describe(doc, lang=ctx.lang, base=ctx.currency)


def reaction_key(chat_id: str, update_id: int, kind: str) -> str:
    """categoria (gasto) or fuente (ingreso) registered by this update, else "".

    Doc ids are deterministic, so every path (quick, LLM, buttons) reads the
    same doc; a multi-item gasto uses its first item.
    """
    doc_id = f"{update_id}-0" if kind == "gasto" else f"{update_id}-i0"
    snap = _col(chat_id).document(doc_id).get()
    data = snap.to_dict() if snap.exists else {}
    return str(data.get("categoria") or data.get("fuente") or "").strip().lower()


def _reversal(ctx: ToolContext, doc_id: str, d: dict) -> dict:
    """Negative copy of a registro; ``reversa`` names the registro it cancels."""
    rev = {**d, "monto": str(-q(d["monto"])), "update_id": ctx.update_id}
    if "monto_original" in d:
        rev["monto_original"] = str(-q(d["monto_original"]))
    return {**rev, "tipo": "reverso", "reversa": doc_id}


def undo(ctx: ToolContext, batch_id: str | None = None) -> str:
    batch = batch_id or _state().last_batch(ctx.chat_id)
    if not batch:
        return t(ctx.lang, "nothing_to_undo")
    query = _col(ctx.chat_id).where(filter=FieldFilter("batch_id", "==", batch))
    rows = [(s.id, s.to_dict()) for s in query.stream()]
    records = [(i, d) for i, d in rows if d["tipo"] == "registro"]
    if not records:
        return t(ctx.lang, "batch_not_found")
    done = t(ctx.lang, "undone", n=len(records))
    already = t(ctx.lang, "already_undone")
    previous = [d for _, d in rows if d["tipo"] == "reverso"]
    if previous:
        # Same update = Pub/Sub retry: report success again, write nothing.
        retry = all(d["update_id"] == ctx.update_id for d in previous)
        return done if retry else already
    reversals = {
        f"{batch}-r{i}": _reversal(ctx, doc_id, d)
        for i, (doc_id, d) in enumerate(records)
    }
    return done if _create(ctx.chat_id, reversals) else already


# ponytail: scans the last max(50, 10n) writes; movements older than that (behind
# many reversos) are not listed. Page further back if users edit old rows.
def _latest_active(ctx: ToolContext, n: int) -> list[tuple[str, dict]]:
    """Last n registros not cancelled by a reverso, newest first."""
    query = (
        _col(ctx.chat_id)
        .order_by("creado", direction=firestore.Query.DESCENDING)
        .limit(max(50, 10 * n))
    )
    docs = [(s.id, s.to_dict()) for s in query.stream()]
    reversals = [d for _, d in docs if d["tipo"] == "reverso"]
    voided = {d["reversa"] for d in reversals if "reversa" in d}
    # Reversos written before ``reversa`` existed cancel their whole batch.
    batches = {d["batch_id"] for d in reversals if "reversa" not in d}
    return [
        (i, d)
        for i, d in docs
        if d["tipo"] == "registro" and i not in voided and d["batch_id"] not in batches
    ][:n]


def latest(ctx: ToolContext, n: int = 5) -> list[dict]:
    out = []
    for index, (doc_id, d) in enumerate(_latest_active(ctx, n), start=1):
        entry = {
            "index": index,
            "id": doc_id,
            "fecha": d["fecha"],
            "tipo_mov": d["tipo_mov"],
            "monto": d["monto"],
            "monto_original": d.get("monto_original", d["monto"]),
            "moneda_original": d.get("moneda_original", d.get("moneda", "USD")),
            "nota": d.get("nota", ""),
        }
        field = "categoria" if d["tipo_mov"] == "gasto" else "fuente"
        entry[field] = d.get(field, "")
        out.append(entry)
    return out


def latest_text(ctx: ToolContext, n: int = 5) -> str:
    lines = [
        f"{m['index']}) {date.fromisoformat(m['fecha']):%d/%m} "
        f"{describe(m, ' ', ctx.lang, ctx.currency)}"
        for m in latest(ctx, n)
    ]
    return "\n".join(lines) or t(ctx.lang, "no_entries")


def _already_written(ctx: ToolContext) -> dict | None:
    """Docs this update already wrote with edit/void (a Pub/Sub retry)."""
    query = _col(ctx.chat_id).where(
        filter=FieldFilter("update_id", "==", ctx.update_id)
    )
    docs = {s.id: s.to_dict() for s in query.stream()}
    rev = [d for i, d in docs.items() if d["tipo"] == "reverso" and i.endswith("-x")]
    if not rev:
        return None
    return docs.get(f"{ctx.update_id}-e0", rev[0])


def _pick(ctx: ToolContext, index: int) -> tuple[str, dict] | None:
    if index < 1:
        return None
    entries = _latest_active(ctx, index)
    return entries[index - 1] if len(entries) >= index else None


def void(ctx: ToolContext, index: int = 1) -> str:
    previous = _already_written(ctx)
    if previous is not None:
        return t(
            ctx.lang,
            "voided",
            entry=describe(previous, lang=ctx.lang, base=ctx.currency),
        )
    chosen = _pick(ctx, index)
    if chosen is None:
        return t(ctx.lang, "not_found")
    doc_id, d = chosen
    # Reverso id per registro: two updates can never cancel the same row twice.
    if not _create(ctx.chat_id, {f"{doc_id}-x": _reversal(ctx, doc_id, d)}):
        return t(ctx.lang, "not_found")
    return t(ctx.lang, "voided", entry=describe(d, lang=ctx.lang, base=ctx.currency))


def of_day(chat_id: str, day: date) -> list[dict]:
    """Registros of one day still in force (not reversed), oldest first."""
    return active_entries(chat_id, day, day)


def active_entries(chat_id: str, since: date, until: date) -> list[dict]:
    """Registros in the inclusive range still in force (not reversed), oldest
    first. A reverso keeps its registro's fecha, so both fall in the range."""
    end = (until + timedelta(days=1)).isoformat()
    query = (
        _col(chat_id)
        .where(filter=FieldFilter("fecha", ">=", since.isoformat()))
        .where(filter=FieldFilter("fecha", "<", end))
    )
    docs = [(s.id, s.to_dict()) for s in query.stream()]
    reversals = [d for _, d in docs if d.get("tipo") == "reverso"]
    voided = {d["reversa"] for d in reversals if d.get("reversa")}
    # Reversos written before the reversa field cancel their whole batch.
    batches = {d["batch_id"] for d in reversals if not d.get("reversa")}
    alive = [
        d
        for doc_id, d in docs
        if d.get("tipo") != "reverso"
        and doc_id not in voided
        and d.get("batch_id") not in batches
    ]
    return sorted(alive, key=lambda d: str(d.get("creado", "")))


def spend_by_category(
    chat_id: str, since: date, until: date, base: str = "USD"
) -> dict[str, Decimal]:
    """Net spend per category (registro + reverso) in the inclusive range."""
    totals: dict[str, Decimal] = {}
    for d in _by_date(chat_id, "gasto", since, until):
        cat = d["categoria"]
        totals[cat] = totals.get(cat, Decimal(0)) + in_currency(d, base)
    return totals


def total_income(chat_id: str, since: date, until: date, base: str = "USD") -> Decimal:
    docs = _by_date(chat_id, "ingreso", since, until)
    return sum((in_currency(d, base) for d in docs), Decimal("0.00"))


def finance_summary(ctx: ToolContext, period: str) -> str:
    since, until = date_range(period, today(ctx))
    expenses = spend_by_category(ctx.chat_id, since, until, ctx.currency)
    total = sum(expenses.values(), Decimal("0.00"))
    income = total_income(ctx.chat_id, since, until, ctx.currency)
    text = f"{period}: gastos {total} {ctx.currency}, ingresos {income} {ctx.currency}"
    top = max(expenses, key=lambda c: expenses[c], default=None)
    if top is not None and expenses[top] > 0:
        text += f"; mayor {top} {expenses[top]}"
    return text
