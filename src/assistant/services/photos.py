"""Photos read by Gemini: a meal (estimated kcal and macros) or a receipt split
between people (who still owes the owner).

Stored field names are Spanish, like the rest of Firestore:

- ``comidas/{chat_id}/registros/{id}``: fecha (YYYY-MM-DD, user's zone),
  nombre, kcal, proteina, carbohidratos, grasa, creado.
- ``cuentas/{chat_id}/divisiones/{id}``: fecha, titulo, total, moneda,
  personas, deudores ``[{nombre, monto, pagado}]`` (monto as a string),
  abierta, creado.

The photo itself is never stored. Neither is an expense: the owner records
their own share by hand.
"""

from __future__ import annotations

import base64
import json
import logging
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

import httpx
from google.cloud import firestore

from assistant.context import ToolContext
from assistant.services import ledger, state

logger = logging.getLogger(__name__)

GEMINI_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
)
ME = {"yo", "me", "i", "mi", "我"}
MAX_PEOPLE = 20
OPEN_SPLITS = 10

_STR = {"type": "STRING"}
_INT = {"type": "INTEGER"}
_NUM = {"type": "NUMBER"}
SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "kind": {"type": "STRING", "enum": ["meal", "receipt", "other"]},
        "name": _STR,
        "kcal": _INT,
        "protein_g": _INT,
        "carbs_g": _INT,
        "fat_g": _INT,
        "total": _NUM,
        "currency": _STR,
        "people": _INT,
        "items": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {"name": _STR, "price": _NUM, "person": _STR},
                "required": ["name", "price"],
            },
        },
    },
    # Every field, so the model never skips kcal; unused ones come back 0 or "".
    "required": [
        "kind",
        "name",
        "kcal",
        "protein_g",
        "carbs_g",
        "fat_g",
        "total",
        "currency",
        "people",
        "items",
    ],
}
PROMPT = """\
Read this photo. The user's note: "{caption}". Answer in language "{lang}".
- Food or drink about to be eaten: kind=meal; name = a short dish name; kcal \
and macros (grams) for the portion shown, adjusted by the note (e.g. "half").
- A receipt or bill: kind=receipt; total = the final amount to pay as printed \
(tax and tip included); currency = ISO 4217 code ("{currency}" if unclear); \
name = a short title from the note (else the place); people = how many people \
split it per the note (0 if it does not say); items = each product line with \
its price (not subtotal, tax, tip or total), and person = the name the note \
gives that item (empty if none).
- Anything else: kind=other.
Amounts are plain numbers in the receipt's currency: a "." or "," that groups \
thousands is not a decimal point (COP 168.300 = 168300).
Fields that do not apply: 0, "" or []."""


class PhotoUnavailable(Exception):
    """Gemini failed or is not configured."""


def analyze(
    image: bytes, caption: str, ctx: ToolContext, api_key: str, model: str
) -> dict:
    """One Gemini call; the parsed JSON (see SCHEMA)."""
    if not api_key:
        raise PhotoUnavailable("no key")
    prompt = PROMPT.format(caption=caption[:300], lang=ctx.lang, currency=ctx.currency)
    body = {
        "contents": [
            {
                "parts": [
                    {
                        "inline_data": {
                            "mime_type": "image/jpeg",
                            "data": base64.b64encode(image).decode(),
                        }
                    },
                    {"text": prompt},
                ]
            }
        ],
        "generationConfig": {
            "responseMimeType": "application/json",
            "responseSchema": SCHEMA,
        },
    }
    try:
        resp = httpx.post(
            GEMINI_URL.format(model=model),
            headers={"x-goog-api-key": api_key},
            json=body,
            timeout=30,
        )
        resp.raise_for_status()
        text = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
        return _thousands(dict(json.loads(text)))
    except (httpx.HTTPError, KeyError, IndexError, ValueError, TypeError) as exc:
        raise PhotoUnavailable(type(exc).__name__) from exc


# Currencies without cents in practice; Gemini sometimes reads COP 168.300 as
# 168.3 despite the prompt.
NO_CENTS = {"COP", "CLP", "PYG", "JPY", "KRW", "VND", "IDR"}


def _thousands(data: dict) -> dict:
    """A fractional amount in a currency without cents was a misread thousands
    separator: scale the total and the items by 1000."""
    total = Decimal(str(data.get("total") or 0))
    if str(data.get("currency", "")).upper() not in NO_CENTS or total == int(total):
        return data
    data["total"] = str(total * 1000)
    for it in data.get("items") or []:
        it["price"] = str(Decimal(str(it.get("price") or 0)) * 1000)
    return data


# --- split -----------------------------------------------------------------------


def _round(value: Decimal, exact: bool) -> Decimal:
    step = Decimal("0.01") if exact else Decimal("1")
    return value.quantize(step, rounding=ROUND_HALF_UP)


def split(total: Decimal, people: int, items: list[dict]) -> list[tuple[str, Decimal]]:
    """Shares of everyone but the owner, as (name, amount).

    Items the note assigns to a name are that person's; the rest is shared
    equally. Tax, tip or discounts (total vs the sum of items) scale every share
    alike. Unnamed people are numbered. The owner's share absorbs the rounding.
    """
    named: dict[str, Decimal] = {}
    for it in items:
        who = str(it.get("person") or "").strip()
        if who:
            key = "yo" if who.lower() in ME else who
            named[key] = named.get(key, Decimal(0)) + Decimal(str(it["price"]))
    others = [n for n in named if n != "yo"]
    n = min(max(people, len(others) + 1, 2), MAX_PEOPLE)
    priced = sum((Decimal(str(it["price"])) for it in items), Decimal(0))
    if not named or priced <= 0:  # equal split
        named, priced = {}, total
    factor = total / priced
    shared = (priced - sum(named.values(), Decimal(0))) / n
    exact = total != total.to_integral()
    debtors = [
        (name, _round((named[name] + shared) * factor, exact)) for name in others
    ]
    debtors += [
        (f"👤{i}", _round(shared * factor, exact)) for i in range(1, n - len(others))
    ]
    return debtors


def save_split(
    ctx: ToolContext,
    title: str,
    total: Decimal,
    currency: str,
    debtors: list[tuple[str, Decimal]],
) -> str:
    ref = _splits(ctx.chat_id).document()
    ref.set(
        {
            "fecha": ledger.today(ctx).isoformat(),
            "titulo": title[:40],
            "total": str(total),
            "moneda": currency,
            "personas": len(debtors) + 1,
            "deudores": [
                {"nombre": n, "monto": str(a), "pagado": False} for n, a in debtors
            ],
            "abierta": True,
            "creado": firestore.SERVER_TIMESTAMP,
        }
    )
    return str(ref.id)


def mark_paid(chat_id: str, split_id: str, index: int) -> dict | None:
    """Mark one debtor paid; the updated split, or None if it does not exist."""
    ref = _splits(chat_id).document(split_id)
    snap = ref.get()
    if not snap.exists:
        return None
    data = snap.to_dict()
    debtors = data["deudores"]
    if 0 <= index < len(debtors):
        debtors[index]["pagado"] = True
    data["abierta"] = not all(d["pagado"] for d in debtors)
    ref.set(data)
    return data


def open_splits(chat_id: str) -> list[tuple[str, dict]]:
    query = _splits(chat_id).where(filter=firestore.FieldFilter("abierta", "==", True))
    rows = [(s.id, s.to_dict()) for s in query.stream()]
    return sorted(rows, key=lambda r: r[1]["fecha"])[-OPEN_SPLITS:]


def _splits(chat_id: str) -> Any:
    return state._db().collection("cuentas").document(chat_id).collection("divisiones")


# --- meals -----------------------------------------------------------------------


def add_meal(ctx: ToolContext, meal: dict) -> str:
    ref = _meals(ctx.chat_id).document()
    ref.set(
        {
            "fecha": ledger.today(ctx).isoformat(),
            "nombre": str(meal.get("name") or "?")[:40],
            "kcal": int(meal.get("kcal") or 0),
            "proteina": int(meal.get("protein_g") or 0),
            "carbohidratos": int(meal.get("carbs_g") or 0),
            "grasa": int(meal.get("fat_g") or 0),
            "creado": firestore.SERVER_TIMESTAMP,
        }
    )
    return str(ref.id)


def kcal_today(ctx: ToolContext) -> int:
    day = ledger.today(ctx).isoformat()
    query = _meals(ctx.chat_id).where(filter=firestore.FieldFilter("fecha", "==", day))
    return sum(int(s.to_dict().get("kcal", 0)) for s in query.stream())


def delete_meal(chat_id: str, meal_id: str) -> None:
    _meals(chat_id).document(meal_id).delete()


def _meals(chat_id: str) -> Any:
    return state._db().collection("comidas").document(chat_id).collection("registros")
