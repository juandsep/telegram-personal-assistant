import dataclasses
import sys
from datetime import date, datetime
from decimal import Decimal
from unittest.mock import MagicMock
from zoneinfo import ZoneInfo

import pytest

from assistant.context import ToolContext
from assistant.services import budgets, fx, ledger

D = Decimal
CTX = ToolContext(
    "42", "owner", "USD", "America/Panama", 1,
    datetime(2026, 9, 29, 12, tzinfo=ZoneInfo("America/Panama")),
)  # fmt: skip


def test_503020_picks_bucket_with_largest_excess() -> None:
    expenses = {"restaurantes": D("250"), "viajes": D("100"), "vivienda": D("520")}
    # Income 1000: necesidades cap 500 (+20), ocio cap 300 (+50).
    assert budgets.largest_excess(expenses, None, D("1000")) == (
        "ocio",
        D("350"),
        D("300.00"),
    )


def test_503020_saving_more_is_not_an_excess() -> None:
    assert budgets.largest_excess({"ahorro": D("900")}, None, D("1000")) is None


def test_per_category_budget_wins_and_prorates() -> None:
    expenses = {"supermercado": D("120"), "restaurantes": D("90")}
    budget = {"supermercado": "100", "restaurantes": "60"}
    assert budgets.largest_excess(expenses, budget, D("0")) == (
        "restaurantes",
        D("90"),
        D("60.00"),
    )
    assert budgets.largest_excess(expenses, budget, D(0), factor=D(2)) is None


@pytest.fixture
def prefs(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    mod = MagicMock()
    mod.get_preferences.return_value = {}
    monkeypatch.setitem(sys.modules, "assistant.services.state", mod)
    return mod


def test_recommend_budget_messages(
    monkeypatch: pytest.MonkeyPatch, prefs: MagicMock
) -> None:
    calls: list[tuple[date, date]] = []

    def expenses(chat_id: str, since: date, until: date, base: str) -> dict[str, D]:
        calls.append((since, until))
        return {"restaurantes": D("400.00")}

    income = MagicMock(return_value=D("0.00"))
    monkeypatch.setattr(ledger, "spend_by_category", expenses)
    monkeypatch.setattr(ledger, "total_income", income)
    assert budgets.recommend_budget(CTX) == (
        "Sin presupuesto ni ingresos del mes para comparar."
    )
    assert calls[-1] == (date(2026, 9, 1), date(2026, 9, 29))
    income.return_value = D("1000.00")
    assert budgets.recommend_budget(CTX).startswith(
        "Exceso en Ocio (50/30/20): 400.00 de 300.00 USD (+100.00)."
    )
    prefs.get_preferences.return_value = {"presupuesto": {"restaurantes": "500"}}
    assert budgets.recommend_budget(CTX) == "Dentro del presupuesto."
    # A week pro-rates the monthly cap: 500 * 2/30 over Mon-Tue.
    assert budgets.recommend_budget(CTX, "semana").startswith(
        "Exceso en Restaurantes: 400.00 de 33.33 USD"
    )


def test_caps_in_usd_compare_in_user_currency(
    monkeypatch: pytest.MonkeyPatch, prefs: MagicMock
) -> None:
    bases: list[str] = []

    def expenses(chat_id: str, since: date, until: date, base: str) -> dict[str, D]:
        bases.append(base)
        return {"restaurantes": D("400000.00")}  # already in COP

    monkeypatch.setattr(ledger, "spend_by_category", expenses)
    monkeypatch.setattr(ledger, "total_income", MagicMock(return_value=D(0)))
    monkeypatch.setattr(fx, "rate", lambda cur, day: (D("4000"), "trm"))
    prefs.get_preferences.return_value = {"presupuesto": {"restaurantes": "50"}}
    cop = dataclasses.replace(CTX, currency="COP")
    assert budgets.recommend_budget(cop).startswith(
        "Exceso en Restaurantes: 400000.00 de 200000.00 COP (+200000.00)."
    )
    assert bases == ["COP"]
