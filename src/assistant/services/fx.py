"""Conversion to USD at the day's rate, done in code (never by the LLM).

- COP: official TRM from datos.gov.co (dataset ``32sa-8pi3``), the latest row
  with ``vigenciadesde <= fecha``. Source ``trm``.
- ECB currencies: Frankfurter ``/v1/{day}?base=USD``. Source ``ecb``.
- USD: no lookup, rate 1. Source ``usd``.

A rate is "units of currency per 1 USD" and is cached in Firestore
``fx/{YYYY-MM-DD}_{CUR}`` (public data, plain values). Any failure raises
``FxError`` with a short code; logs carry only that code and the currency.
"""

from __future__ import annotations

import logging
import os
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from functools import cache

import httpx
from google.cloud import firestore

log = logging.getLogger(__name__)

TRM_URL = "https://www.datos.gov.co/resource/32sa-8pi3.json"
ECB_URL = "https://api.frankfurter.dev/v1/{day}"
# Currencies the ECB (Frankfurter) publishes against USD.
ECB = frozenset(
    "AUD BGN BRL CAD CHF CNY CZK DKK EUR GBP HKD HUF IDR ILS INR ISK JPY KRW "
    "MXN MYR NOK NZD PHP PLN RON SEK SGD THB TRY ZAR".split()
)
CENT = Decimal("0.01")


class FxError(Exception):
    """Short code: unsupported|http|data|cache."""


@cache
def _db() -> firestore.Client:
    return firestore.Client(
        project=os.environ.get("GCP_PROJECT_ID") or None,
        database=os.environ.get("FIRESTORE_DATABASE") or None,  # staging has its own
    )


def _get(url: str, params: dict[str, str]) -> object:
    # httpx does not follow redirects by default: a 3xx is a failure here.
    r = httpx.get(url, params=params, timeout=5.0)
    if r.status_code != 200:
        raise FxError("http")
    return r.json(parse_float=Decimal)


def _fetch_rate(currency: str, day: date) -> tuple[Decimal, str]:
    if currency == "COP":
        day_start = f"{day.isoformat()}T00:00:00"
        rows = _get(
            TRM_URL,
            {
                "$where": f"vigenciadesde <= '{day_start}'",
                "$order": "vigenciadesde DESC",
                "$limit": "1",
            },
        )
        if not isinstance(rows, list) or not rows:
            raise FxError("data")
        return Decimal(str(rows[0]["valor"])), "trm"
    data = _get(
        ECB_URL.format(day=day.isoformat()), {"base": "USD", "symbols": currency}
    )
    if not isinstance(data, dict):
        raise FxError("data")
    return Decimal(str(data["rates"][currency])), "ecb"


def rate(currency: str, day: date) -> tuple[Decimal, str]:
    """(units of currency per 1 USD, source), cached per day and currency."""
    if currency == "USD":
        return Decimal(1), "usd"
    if currency != "COP" and currency not in ECB:
        raise FxError("unsupported")
    try:
        ref = _db().collection("fx").document(f"{day.isoformat()}_{currency}")
        snap = ref.get()
        if snap.exists:
            d = snap.to_dict() or {}
            return Decimal(d["tasa"]), d["fuente"]
        value, source = _fetch_rate(currency, day)
        if value <= 0:
            raise FxError("data")
        ref.set({"tasa": str(value), "fuente": source})
        return value, source
    except FxError as e:
        log.warning("fx_failed code=%s moneda=%s", e, currency)
        raise
    except httpx.HTTPError as e:
        log.warning("fx_failed code=%s moneda=%s", type(e).__name__, currency)
        raise FxError("http") from e
    except (KeyError, ArithmeticError, ValueError, TypeError) as e:
        log.warning("fx_failed code=%s moneda=%s", type(e).__name__, currency)
        raise FxError("data") from e
    except Exception as e:  # Firestore cache down
        log.warning("fx_failed code=%s moneda=%s", type(e).__name__, currency)
        raise FxError("cache") from e


def to_usd(amount: Decimal, currency: str, day: date) -> tuple[Decimal, Decimal, str]:
    """(USD rounded to cents, rate as currency per 1 USD, source)."""
    currency = currency.strip().upper()
    value, source = rate(currency, day)
    usd = (Decimal(str(amount)) / value).quantize(CENT, rounding=ROUND_HALF_UP)
    return usd, value, source
