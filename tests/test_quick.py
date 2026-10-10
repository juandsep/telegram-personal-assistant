from decimal import Decimal

import pytest

from assistant.services.quick import NOT_POSITIVE, parse


@pytest.mark.parametrize(
    ("text", "kind", "amount", "currency", "note", "category"),
    [
        ("gasto 2 usd cafe", "gasto", "2", "USD", "café", "restaurantes"),
        ("2 usd cafe", "gasto", "2", "USD", "café", "restaurantes"),
        ("cafe 2000cop gasto", "gasto", "2000", "COP", "café", "restaurantes"),
        ("2000 cop cafe", "gasto", "2000", "COP", "café", "restaurantes"),
        ("1000usd ingreso", "ingreso", "1000", "USD", "", ""),
        ("ingreso 1000 salario", "ingreso", "1000", "USD", "salario", ""),
        ("cafe 5", "gasto", "5", "USD", "café", "restaurantes"),
        ("Café 2.5", "gasto", "2.5", "USD", "Café", "restaurantes"),
        ("almuerzo 2,5", "gasto", "2.5", "USD", "almuerzo", "restaurantes"),
        ("2,000 cop taxi", "gasto", "2000", "COP", "taxi", "transporte"),
        ("mercado 2.000 cop", "gasto", "2000", "COP", "mercado", "supermercado"),
        ("1.234,56 cop arriendo", "gasto", "1234.56", "COP", "arriendo", "vivienda"),
        ("1,234.56 mxn luz", "gasto", "1234.56", "MXN", "luz", "servicios"),
        ("1.000.000 cop", "", "1000000", "COP", "", "otros"),  # bare: ask
        ("5", "", "5", "USD", "", "otros"),
        ("+500 salario", "ingreso", "500", "USD", "salario", ""),
        ("+20 usd", "ingreso", "20", "USD", "", ""),
        ("-5 cafe", "gasto", "5", "USD", "café", "restaurantes"),
        ("\u22125 cafe", "gasto", "5", "USD", "café", "restaurantes"),
        ("gasto 7", "gasto", "7", "USD", "", "otros"),
        ("ingreso 900", "ingreso", "900", "USD", "", ""),
        ("$3.50 uber", "gasto", "3.50", "USD", "uber", "transporte"),
        ("5€ cine", "gasto", "5", "EUR", "cine", "entretenimiento"),
        ("usd 2 netflix", "gasto", "2", "USD", "netflix", "suscripciones"),
        ("2 xyz farmacia", "gasto", "2", "USD", "xyz farmacia", "salud"),
        ("ropa 20 PEN", "gasto", "20", "PEN", "ropa", "compras"),
        ("gasté 5 en pan", "gasto", "5", "USD", "pan", "otros"),
        ("INGRESO 2,000 Freelance", "ingreso", "2000", "USD", "Freelance", ""),
    ],
)
def test_parse_accepts(text, kind, amount, currency, note, category) -> None:
    e = parse(text)
    assert e is not None and e.error is None
    assert (e.kind, e.amount, e.currency, e.note, e.category) == (
        kind,
        Decimal(amount),
        currency,
        note,
        category,
    )
    assert isinstance(e.amount, Decimal)


@pytest.mark.parametrize("text", ["0 cafe", "-0 cafe", "cafe 0,00"])
def test_not_positive_is_an_error_entry(text) -> None:
    e = parse(text)
    assert e is not None and e.error == NOT_POSITIVE


@pytest.mark.parametrize(
    "text",
    [
        "",
        "hola",
        "cafe 5 y pan 3",
        "2 usd 3 cop",
        "mañana a las 4 dentista",
        "dentista 4pm 5",
        "16:00 cafe 5",
        "cafe 5 hoy",
        "lunes gym 5",
        "¿cuánto gasté?",
        "cuanto gaste en cafe 5",
        "el último era 3 dólares, no 5",
        "cambia el ultimo a 3",
        "recuérdame pagar 5",
        "/anular 1",
        "5/10 cafe",
        "1.2,3 cafe",
        "cafe 5 con juan en el centro de la ciudad",
    ],
)
def test_parse_leaves_everything_else_to_the_llm(text) -> None:
    assert parse(text) is None


@pytest.mark.parametrize(
    ("text", "kind", "category"),
    [
        ("-12 lunch", "gasto", "restaurantes"),
        ("20 groceries", "gasto", "supermercado"),
        ("12 dollars dinner", "gasto", "restaurantes"),
        ("1000 income", "ingreso", ""),
        ("-12 午饭", "gasto", "restaurantes"),
        ("买咖啡 5", "gasto", "restaurantes"),  # keyword inside a Chinese word
        ("30 超市", "gasto", "supermercado"),
        ("8 书", "gasto", "otros"),
    ],
)
def test_english_and_chinese_keywords(text, kind, category) -> None:
    e = parse(text)
    assert e is not None and (e.kind, e.category) == (kind, category)


@pytest.mark.parametrize(
    "text", ["lunch tomorrow 12", "how much 5", "明天 午饭 12", "多少 5", "5 吗？"]
)
def test_english_and_chinese_dates_and_questions_go_to_llm(text) -> None:
    assert parse(text) is None


@pytest.mark.parametrize(
    ("text", "kind", "note"),
    [("- 5 usd", "gasto", ""), ("+ 5 salario", "ingreso", "salario")],
)
def test_detached_sign_joins_the_amount(text, kind, note) -> None:
    e = parse(text)
    assert e is not None and (e.kind, e.amount, e.note) == (kind, Decimal(5), note)


@pytest.mark.parametrize("text", ["–5usd", "—5usd"])  # en, em dash
def test_dashes_are_a_minus_sign(text) -> None:
    e = parse(text)
    assert e is not None and (e.kind, e.amount, e.currency) == ("gasto", 5, "USD")


@pytest.mark.parametrize("text", ["5 cny", "5 yuan", "5 rmb", "5元", "5 人民币", "5块"])
def test_chinese_yuan(text) -> None:
    e = parse(text)
    assert e is not None and (e.amount, e.currency, e.note) == (Decimal(5), "CNY", "")


def test_note_gets_its_spanish_accent() -> None:
    notes = [parse(t).note for t in ("15 cafe", "medico 30", "5 lunch")]
    assert notes == ["café", "médico", "lunch"]


def test_default_currency() -> None:
    assert parse("5 cafe", default="COP").currency == "COP"
    assert parse("5 usd cafe", default="COP").currency == "USD"


@pytest.mark.parametrize(
    ("text", "amount", "currency", "note"),
    [
        ("-5Cafe", Decimal(5), "USD", "café"),
        ("3euros cena", Decimal(3), "EUR", "cena"),
        ("25000cop mercado", Decimal(25000), "COP", "mercado"),
    ],
)
def test_word_glued_to_the_amount_is_split(text, amount, currency, note) -> None:
    entry = parse(text)
    assert entry is not None
    assert (entry.amount, entry.currency, entry.note) == (amount, currency, note)


def test_pounds() -> None:
    for text in ("£12 taxi", "12 gbp taxi", "12 libras taxi"):
        entry = parse(text, default="USD")
        assert entry is not None and entry.currency == "GBP", text
