import copy
import dataclasses
import sys
from datetime import UTC, date, datetime
from decimal import Decimal
from unittest.mock import MagicMock
from zoneinfo import ZoneInfo

import httpx
import pytest
import respx
from firestore_fake import FakeDB

from assistant.context import ToolContext
from assistant.services import fx, ledger

PANAMA = ZoneInfo("America/Panama")


def make_ctx(update_id: int = 100, chat_id: str = "42") -> ToolContext:
    now = datetime(2026, 9, 29, 12, tzinfo=PANAMA)
    return ToolContext(chat_id, "owner", "USD", "America/Panama", update_id, now)


@pytest.fixture
def db(monkeypatch: pytest.MonkeyPatch) -> FakeDB:
    fake = FakeDB()
    monkeypatch.setattr(ledger, "_db", lambda: fake)
    monkeypatch.setattr(fx, "_db", lambda: fake)
    return fake


@pytest.fixture
def state(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    mod = MagicMock()
    monkeypatch.setitem(sys.modules, "assistant.services.state", mod)
    return mod


ITEMS = [
    {"amount": 2, "category": "supermercado", "note": "pan"},
    {"amount": 3.005, "category": "supermercado"},
]
BASE = "ledger/42/movimientos"


@respx.mock  # USD: any HTTP call would fail as unmatched
def test_expense_writes_decimal_strings(db: FakeDB, state: MagicMock) -> None:
    out = ledger.record_expense(make_ctx(), ITEMS, "USD", date(2026, 9, 29))
    assert out == "−2.00 USD · Pan · Mercado; −3.01 USD · Mercado"
    assert sorted(db.store) == [f"{BASE}/100-0", f"{BASE}/100-1"]
    assert db.store[f"{BASE}/100-0"] == {
        "fecha": "2026-09-29",
        "monto": "2.00",
        "moneda": "USD",
        "monto_original": "2.00",
        "moneda_original": "USD",
        "tasa": "1",
        "fuente_tasa": "usd",
        "categoria": "supermercado",
        "tipo_mov": "gasto",
        "nota": "pan",
        "batch_id": "g100",
        "update_id": 100,
        "tipo": "registro",
        "creado": db.now,
    }
    assert db.store[f"{BASE}/100-1"]["monto"] == "3.01"
    state.set_last_batch.assert_called_with("42", "g100")


def test_retry_of_same_update_writes_nothing(db: FakeDB, state: MagicMock) -> None:
    first = ledger.record_expense(make_ctx(), ITEMS, "USD", date(2026, 9, 29))
    before = copy.deepcopy(db.store)
    again = ledger.record_expense(make_ctx(), ITEMS, "USD", date(2026, 9, 29))
    assert again == first
    assert db.store == before and db.commits == 1
    assert state.set_last_batch.call_count == 2
    # Another chat with the same update_id is not affected.
    ledger.record_expense(make_ctx(chat_id="7"), ITEMS[:1], "USD", date(2026, 9, 29))
    assert "ledger/7/movimientos/100-0" in db.store


def test_income_idempotent(db: FakeDB, state: MagicMock) -> None:
    for _ in range(2):
        out = ledger.record_income(
            make_ctx(), Decimal("1000"), "USD", "salario", date(2026, 9, 1), "sep"
        )
    assert out == "+1000.00 USD · Sep"
    assert list(db.store) == [f"{BASE}/100-i0"]
    doc = db.store[f"{BASE}/100-i0"]
    assert (doc["fuente"], doc["tipo_mov"], doc["nota"]) == (
        "salario",
        "ingreso",
        "sep",
    )
    state.set_last_batch.assert_called_with("42", "i100")


def test_rejects_non_positive(db: FakeDB, state: MagicMock) -> None:
    out = ledger.record_expense(
        make_ctx(), [{"amount": 0, "category": "otros"}], "USD", date(2026, 9, 29)
    )
    assert out == "El monto debe ser mayor que 0."
    out = ledger.record_income(make_ctx(), Decimal("-1"), "USD", "x", date(2026, 9, 29))
    assert out == "El monto debe ser mayor que 0."
    assert not db.store


def test_undo_appends_reversal_and_never_edits(db: FakeDB, state: MagicMock) -> None:
    ledger.record_expense(make_ctx(), ITEMS, "USD", date(2026, 9, 29))
    before = copy.deepcopy(db.store)
    state.last_batch.return_value = "g100"
    assert ledger.undo(make_ctx(update_id=101)) == "↩ deshecho: 2 fila(s)"
    assert {k: db.store[k] for k in before} == before  # originals untouched
    rev = db.store[f"{BASE}/g100-r0"]
    assert (rev["monto"], rev["batch_id"], rev["update_id"], rev["tipo"]) == (
        "-2.00",
        "g100",
        101,
        "reverso",
    )
    assert db.store[f"{BASE}/g100-r1"]["monto"] == "-3.01"
    # Retry of the same update: success, no new docs. Another update: refused.
    assert ledger.undo(make_ctx(update_id=101)) == "↩ deshecho: 2 fila(s)"
    assert ledger.undo(make_ctx(update_id=102), "g100") == (
        "Ese lote ya estaba deshecho."
    )
    assert len(db.store) == 4 and db.commits == 2


def test_undo_race_reports_already_undone(
    db: FakeDB, state: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    ledger.record_expense(make_ctx(), ITEMS[:1], "USD", date(2026, 9, 29))
    monkeypatch.setattr(ledger, "_create", lambda chat_id, docs: False)
    assert ledger.undo(make_ctx(update_id=101), "g100") == (
        "Ese lote ya estaba deshecho."
    )


def test_undo_edge_cases(db: FakeDB, state: MagicMock) -> None:
    state.last_batch.return_value = None
    assert ledger.undo(make_ctx()) == "Nada que deshacer."
    assert ledger.undo(make_ctx(), "g999") == "Lote no encontrado."
    ledger.record_income(make_ctx(), Decimal(5), "USD", "venta", date(2026, 9, 29))
    # Other chats cannot undo this batch.
    assert ledger.undo(make_ctx(chat_id="7"), "i100") == "Lote no encontrado."
    assert ledger.undo(make_ctx(update_id=101), "i100") == "↩ deshecho: 1 fila(s)"
    assert db.store[f"{BASE}/i100-r0"]["monto"] == "-5.00"
    assert db.store[f"{BASE}/i100-r0"]["fuente"] == "venta"


def test_finance_summary_includes_reversals(db: FakeDB, state: MagicMock) -> None:
    ledger.record_expense(
        make_ctx(update_id=1),
        [{"amount": "45", "category": "restaurantes"}],
        "USD",
        date(2026, 9, 29),
    )
    ledger.record_expense(make_ctx(update_id=2), ITEMS, "USD", date(2026, 9, 28))
    ledger.record_expense(make_ctx(update_id=3), ITEMS, "USD", date(2026, 8, 31))
    ledger.record_income(
        make_ctx(update_id=4), Decimal(900), "USD", "salario", date(2026, 9, 1)
    )
    ledger.undo(make_ctx(update_id=5), "g2")
    assert ledger.finance_summary(make_ctx(), "mes") == (
        "mes: gastos 45.00 USD, ingresos 900.00 USD; mayor restaurantes 45.00"
    )
    assert ledger.spend_by_category("42", date(2026, 9, 28), date(2026, 9, 28)) == {
        "supermercado": Decimal("0.00")
    }
    assert ledger.total_income("42", date(2026, 9, 2), date(2026, 9, 29)) == 0
    assert ledger.finance_summary(make_ctx(chat_id="7"), "hoy") == (
        "hoy: gastos 0.00 USD, ingresos 0.00 USD"
    )


def test_query_entries_by_created(db: FakeDB, state: MagicMock) -> None:
    ledger.record_expense(make_ctx(), ITEMS[:1], "USD", date(2026, 1, 1))
    day = datetime(2026, 9, 29, tzinfo=PANAMA)
    docs = ledger.query_entries("42", "creado", day, day.replace(day=30))
    assert [d["fecha"] for d in docs] == ["2026-01-01"]  # backdated, written today
    assert (
        ledger.query_entries(
            "42", "creado", day.replace(day=30), datetime(2027, 1, 1, tzinfo=UTC)
        )
        == []
    )


def test_date_range() -> None:
    tue = date(2026, 9, 29)
    assert ledger.date_range("hoy", tue) == (tue, tue)
    assert ledger.date_range("semana", tue) == (date(2026, 9, 28), tue)
    assert ledger.date_range("mes", tue) == (date(2026, 9, 1), tue)
    with pytest.raises(ValueError):
        ledger.date_range("año", tue)


def test_q_rounds_half_up_without_float() -> None:
    assert ledger.q(0.1 + 0.2) == Decimal("0.30")
    assert ledger.q("2.675") == Decimal("2.68")
    assert ledger.q("-0.005") == Decimal("-0.01")
    assert str(ledger.q(Decimal("10"))) == "10.00"


def test_db_is_lazy_and_cached(monkeypatch: pytest.MonkeyPatch) -> None:
    ledger._db.cache_clear()
    client = MagicMock()
    monkeypatch.setattr(ledger.firestore, "Client", client)
    assert ledger._db() is ledger._db()
    client.assert_called_once()
    ledger._db.cache_clear()


TRM = "https://www.datos.gov.co/resource/32sa-8pi3.json"
ECB = "https://api.frankfurter.dev/v1/2026-09-29"


def trm(value: str = "4081.63") -> httpx.Response:
    return httpx.Response(
        200,
        json=[
            {
                "valor": value,
                "vigenciadesde": "2026-09-29T00:00:00.000",
                "vigenciahasta": "2026-09-29T00:00:00.000",
            }
        ],
    )


@respx.mock
def test_expense_in_cop_converts_with_trm(db: FakeDB, state: MagicMock) -> None:
    route = respx.get(TRM).mock(return_value=trm())
    items = [{"amount": 2000, "category": "", "note": "café"}]
    out = ledger.record_expense(make_ctx(), items, "COP", date(2026, 9, 29))
    assert out == "−0.49 USD · Café (2,000 COP) · Otros"
    params = route.calls.last.request.url.params
    assert params["$where"] == "vigenciadesde <= '2026-09-29T00:00:00'"
    assert (params["$order"], params["$limit"]) == ("vigenciadesde DESC", "1")
    doc = db.store[f"{BASE}/100-0"]
    assert {k: doc[k] for k in ("monto", "moneda", "categoria")} == {
        "monto": "0.49",
        "moneda": "USD",
        "categoria": "otros",
    }
    assert (doc["monto_original"], doc["moneda_original"]) == ("2000.00", "COP")
    assert (doc["tasa"], doc["fuente_tasa"]) == ("4081.63", "trm")
    assert db.store["fx/2026-09-29_COP"] == {"tasa": "4081.63", "fuente": "trm"}
    # Cached: a second conversion for the same day makes no HTTP call.
    ledger.record_expense(make_ctx(101), items, "cop", date(2026, 9, 29))
    assert route.call_count == 1


@respx.mock
def test_income_in_eur_uses_frankfurter(db: FakeDB, state: MagicMock) -> None:
    route = respx.get(ECB).mock(
        return_value=httpx.Response(200, json={"rates": {"EUR": 0.8}})
    )
    out = ledger.record_income(
        make_ctx(), Decimal("12.5"), "EUR", "", date(2026, 9, 29)
    )
    assert out == "+15.63 USD (12.50 EUR)"
    assert dict(route.calls.last.request.url.params) == {
        "base": "USD",
        "symbols": "EUR",
    }
    doc = db.store[f"{BASE}/100-i0"]
    assert (doc["monto"], doc["tasa"], doc["fuente_tasa"]) == ("15.63", "0.8", "ecb")


@respx.mock
def test_fx_failure_writes_nothing(db: FakeDB, state: MagicMock) -> None:
    respx.get(TRM).mock(return_value=httpx.Response(503))
    respx.get(ECB).mock(side_effect=httpx.ConnectTimeout("slow"))
    items = [{"amount": 5, "category": "otros"}]
    assert ledger.record_expense(make_ctx(), items, "COP", date(2026, 9, 29)) == (
        "No pude obtener la tasa de COP, intenta luego."
    )
    assert ledger.record_income(
        make_ctx(), Decimal(1), "GBP", "x", date(2026, 9, 29)
    ) == ("No pude obtener la tasa de GBP, intenta luego.")
    assert ledger.record_expense(make_ctx(), items, "XYZ", date(2026, 9, 29)) == (
        "Moneda no soportada."
    )
    assert not db.store
    state.set_last_batch.assert_not_called()


@respx.mock
def test_fx_bad_payloads_and_cache_errors(
    db: FakeDB, monkeypatch: pytest.MonkeyPatch
) -> None:
    respx.get(TRM).mock(return_value=httpx.Response(200, json=[]))
    respx.get(ECB).mock(return_value=httpx.Response(200, json={"rates": {}}))
    day = date(2026, 9, 29)
    for currency in ("COP", "EUR"):
        with pytest.raises(fx.FxError, match="data"):
            fx.to_usd(Decimal(1), currency, day)
    respx.get(TRM).mock(return_value=trm("0"))
    with pytest.raises(fx.FxError, match="data"):
        fx.to_usd(Decimal(1), "COP", day)
    assert fx.to_usd(Decimal("3"), "USD", day) == (Decimal("3.00"), 1, "usd")

    def down() -> None:
        raise RuntimeError("firestore down")

    monkeypatch.setattr(fx, "_db", down)
    with pytest.raises(fx.FxError, match="cache"):
        fx.to_usd(Decimal(1), "COP", day)


def test_fx_db_is_lazy(monkeypatch: pytest.MonkeyPatch) -> None:
    fx._db.cache_clear()
    client = MagicMock()
    monkeypatch.setattr(fx.firestore, "Client", client)
    assert fx._db() is fx._db()
    client.assert_called_once()
    fx._db.cache_clear()


def seed(db: FakeDB) -> None:
    """Three movements, newest last: gasto 2 (pan), ingreso 900, gasto 2000 COP."""
    ledger.record_expense(make_ctx(1), ITEMS[:1], "USD", date(2026, 9, 28))
    ledger.record_income(make_ctx(2), Decimal(900), "USD", "salario", date(2026, 9, 29))
    db.store["fx/2026-09-30_COP"] = {"tasa": "4000", "fuente": "trm"}
    ledger.record_expense(
        make_ctx(3), [{"amount": 2000, "note": "café"}], "COP", date(2026, 9, 30)
    )


def test_latest_lists_newest_first_and_skips_reversed(
    db: FakeDB, state: MagicMock
) -> None:
    assert ledger.latest_text(make_ctx()) == "Sin movimientos."
    seed(db)
    assert ledger.latest_text(make_ctx()) == (
        "1) 30/09 −0.50 USD Café (2,000 COP)\n"
        "2) 29/09 +900.00 USD Salario\n"
        "3) 28/09 −2.00 USD Pan"
    )
    first_row = ledger.latest(make_ctx(), 1)
    assert first_row == [
        {
            "index": 1,
            "id": "3-0",
            "fecha": "2026-09-30",
            "tipo_mov": "gasto",
            "monto": "0.50",
            "monto_original": "2000.00",
            "moneda_original": "COP",
            "nota": "café",
            "categoria": "otros",
        }
    ]
    assert ledger.void(make_ctx(10), 2) == "✓ anulado: +900.00 USD · Salario"
    ledger.undo(make_ctx(11), "g1")
    assert [m["id"] for m in ledger.latest(make_ctx())] == ["3-0"]
    # Legacy reversos (no ``reversa``) cancel their whole batch.
    del db.store[f"{BASE}/g1-r0"]["reversa"]
    assert [m["id"] for m in ledger.latest(make_ctx())] == ["3-0"]


def cop_ctx(update_id: int = 50) -> ToolContext:
    return dataclasses.replace(make_ctx(update_id), currency="COP")


def test_totals_in_the_user_currency(
    db: FakeDB, state: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    seed(db)
    monkeypatch.setattr(fx, "rate", lambda cur, day: (Decimal("4000"), "trm"))
    assert ledger.finance_summary(cop_ctx(), "mes") == (
        "mes: gastos 8000.00 COP, ingresos 3600000.00 COP; mayor supermercado 8000.00"
    )
    assert ledger.latest_text(cop_ctx()) == (
        "1) 30/09 −2000.00 COP Café\n"
        "2) 29/09 +3600000.00 COP Salario (900 USD)\n"
        "3) 28/09 −8000.00 COP Pan (2 USD)"
    )
    # The stored ledger is still USD.
    assert db.store[f"{BASE}/3-0"]["monto"] == "0.50"


def test_in_currency(monkeypatch: pytest.MonkeyPatch) -> None:
    cop = {"fecha": "2026-09-30", "monto": "0.50", "moneda_original": "COP"}
    cop["monto_original"] = "2000.00"
    old_row = {"fecha": "2026-09-30", "monto": "2.00"}  # before the *_original fields
    rates = {"EUR": Decimal("0.9"), "COP": Decimal("4000")}
    requested: list[tuple[str, date]] = []

    def rate(cur: str, day: date) -> tuple[Decimal, str]:
        requested.append((cur, day))
        return rates[cur], "ecb"

    monkeypatch.setattr(fx, "rate", rate)
    assert ledger.in_currency(cop, "COP") == Decimal("2000.00")  # exact, no rate
    assert ledger.in_currency(cop, "USD") == Decimal("0.50")
    assert ledger.in_currency(old_row, "USD") == Decimal("2.00")
    assert requested == []
    assert ledger.in_currency(cop, "EUR") == Decimal("0.45")
    assert ledger.in_currency(old_row, "COP") == Decimal("8000.00")
    assert requested == [("EUR", date(2026, 9, 30)), ("COP", date(2026, 9, 30))]
    reverso = {**cop, "monto": "-0.50", "monto_original": "-2000.00"}
    assert ledger.in_currency(reverso, "COP") == Decimal("-2000.00")
    assert ledger.in_currency(reverso, "EUR") == Decimal("-0.45")


def test_reversals_net_out_in_any_currency(
    db: FakeDB, state: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    seed(db)
    ledger.void(make_ctx(60))  # the 2000 COP café
    monkeypatch.setattr(fx, "rate", lambda cur, day: (Decimal("0.9"), "ecb"))
    day = date(2026, 9, 30)
    for base in ("USD", "COP", "EUR"):
        assert ledger.spend_by_category("42", day, day, base) == {
            "otros": Decimal("0.00")
        }


def test_describe_falls_back_to_usd_without_a_rate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def down(cur: str, day: date) -> tuple[Decimal, str]:
        raise fx.FxError("http")

    monkeypatch.setattr(fx, "rate", down)
    d = {"fecha": "2026-09-30", "monto": "2.00", "tipo_mov": "gasto", "nota": "pan"}
    assert ledger.describe(d, base="EUR") == "−2.00 USD · Pan"


@respx.mock  # USD only
def test_of_day_skips_reversed_rows_and_batches(db: FakeDB, state: MagicMock) -> None:
    day = date(2026, 9, 29)
    ledger.record_expense(make_ctx(100), ITEMS, "USD", day)  # g100: 2 rows
    ledger.record_income(make_ctx(101), Decimal(900), "USD", "salario", day)
    ledger.record_expense(make_ctx(102), ITEMS[:1], "USD", date(2026, 9, 30))
    assert [d["monto"] for d in ledger.of_day("42", day)] == ["2.00", "3.01", "900.00"]
    state.last_batch.return_value = "g100"
    ledger.undo(make_ctx(update_id=103))  # reverses the whole batch
    assert [d["monto"] for d in ledger.of_day("42", day)] == ["900.00"]
    assert ledger.of_day("41", day) == []


@respx.mock
def test_reaction_key_of_the_update(db: FakeDB, state: MagicMock) -> None:
    ledger.record_expense(make_ctx(), ITEMS, "USD", date(2026, 9, 29))
    ctx = make_ctx(update_id=101)
    ledger.record_income(ctx, Decimal(5), "USD", " Salario", date(2026, 9, 29))
    assert ledger.reaction_key("42", 100, "gasto") == "supermercado"
    assert ledger.reaction_key("42", 101, "ingreso") == "salario"
    assert ledger.reaction_key("42", 102, "gasto") == ""


def test_display_label_names() -> None:
    assert ledger.display_label("supermercado") == "Mercado"
    assert ledger.display_label("vivienda") == "Arriendo"
    assert ledger.display_label("luz") == "Luz" and ledger.display_label("") == ""
