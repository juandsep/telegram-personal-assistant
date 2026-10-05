from decimal import Decimal

import pytest

from assistant.services.quick import NOT_POSITIVE, amount, parse


@pytest.mark.parametrize(
    ("text", "tipo", "monto", "moneda", "nota", "categoria"),
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
def test_parse_accepts(text, tipo, monto, moneda, nota, categoria) -> None:
    e = parse(text)
    assert e is not None and e.error is None
    assert (e.tipo, e.monto, e.moneda, e.nota, e.categoria) == (
        tipo,
        Decimal(monto),
        moneda,
        nota,
        categoria,
    )
    assert isinstance(e.monto, Decimal)


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
        "/editar 1 3usd",
        "2abc cafe",
        "5/10 cafe",
        "1.2,3 cafe",
        "cafe 5 con juan en el centro de la ciudad",
    ],
)
def test_parse_leaves_everything_else_to_the_llm(text) -> None:
    assert parse(text) is None


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("3usd", (Decimal(3), "USD")),
        ("2000 cop", (Decimal(2000), "COP")),
        ("usd 2", (Decimal(2), "USD")),
        ("3", (Decimal(3), None)),
        ("x", None),
        ("3usd cop", None),
        ("", None),
    ],
)
def test_amount(text, expected) -> None:
    assert amount(text) == expected


@pytest.mark.parametrize(
    ("text", "tipo", "categoria"),
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
def test_english_and_chinese_keywords(text, tipo, categoria) -> None:
    e = parse(text)
    assert e is not None and (e.tipo, e.categoria) == (tipo, categoria)


@pytest.mark.parametrize(
    "text", ["lunch tomorrow 12", "how much 5", "明天 午饭 12", "多少 5", "5 吗？"]
)
def test_english_and_chinese_dates_and_questions_go_to_llm(text) -> None:
    assert parse(text) is None


def test_correccion_in_any_language_and_order() -> None:
    from assistant.services.quick import correccion

    assert correccion("editar: 15 restaurantes") == {
        "monto": Decimal(15),
        "categoria": "restaurantes",
    }
    assert correccion("Edit: lunch 12,50 cop Restaurants") == {
        "monto": Decimal("12.50"),
        "moneda": "COP",
        "categoria": "restaurantes",
        "nota": "lunch",
    }
    assert correccion("修改：15 午饭 餐饮") == {
        "monto": Decimal(15),
        "categoria": "restaurantes",
        "nota": "午饭",
    }
    assert correccion("editar: Transporte") == {"categoria": "transporte"}
    assert correccion("editar:") == {}
    assert correccion("editar la cena 5") is None  # no colon: a normal message
    assert correccion("nota: 5") is None


@pytest.mark.parametrize(
    ("text", "tipo", "nota"),
    [("- 5 usd", "gasto", ""), ("+ 5 salario", "ingreso", "salario")],
)
def test_detached_sign_joins_the_amount(text, tipo, nota) -> None:
    e = parse(text)
    assert e is not None and (e.tipo, e.monto, e.nota) == (tipo, Decimal(5), nota)


@pytest.mark.parametrize("text", ["–5usd", "—5usd"])  # en, em dash
def test_dashes_are_a_minus_sign(text) -> None:
    e = parse(text)
    assert e is not None and (e.tipo, e.monto, e.moneda) == ("gasto", 5, "USD")


@pytest.mark.parametrize("text", ["5 cny", "5 yuan", "5 rmb", "5元", "5 人民币", "5块"])
def test_chinese_yuan(text) -> None:
    e = parse(text)
    assert e is not None and (e.monto, e.moneda, e.nota) == (Decimal(5), "CNY", "")


def test_note_gets_its_spanish_accent() -> None:
    notas = [parse(t).nota for t in ("15 cafe", "medico 30", "5 lunch")]
    assert notas == ["café", "médico", "lunch"]


def test_default_currency() -> None:
    assert parse("5 cafe", default="COP").moneda == "COP"
    assert parse("5 usd cafe", default="COP").moneda == "USD"
