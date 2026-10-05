"""Deterministic quick entry: ``2 usd cafe``, ``1000usd ingreso``. No LLM.

Keywords cover Spanish, English and Chinese (see assistant.i18n). Chinese has
no spaces, so its keywords match inside a word (``买咖啡`` has ``咖啡``).

Type: the word ``ingreso`` or a leading ``+`` means income; ``gasto`` or a
leading ``-`` means expense; any other words default to expense. A bare amount
(``5``, ``5 usd``) has ``tipo == ""``: the worker asks gasto or ingreso.

``parse`` accepts a short message with exactly one amount in any word order and
returns an ``Entry``; anything it is not sure about (two amounts, questions,
dates, times, edits, reminders) returns None so the LLM handles it.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from decimal import Decimal

from assistant.context import CATEGORIES
from assistant.i18n import CATEGORIAS

CODES = frozenset(
    {"USD", "COP", "EUR", "MXN", "PEN", "CLP", "ARS", "BRL", "GBP", "CAD", "PAB", "CNY"}
)
_CUR = {c.lower(): c for c in CODES} | {
    "$": "USD",
    "€": "EUR",
    "dolar": "USD",
    "dolares": "USD",
    "dollar": "USD",
    "dollars": "USD",
    "美元": "USD",
    "euro": "EUR",
    "euros": "EUR",
    "yuan": "CNY",
    "rmb": "CNY",
    "元": "CNY",
    "人民币": "CNY",
    "块": "CNY",
}
# "5元": Chinese currency glued to the number like a symbol.
_TOKEN = re.compile(r"([$€])?([-+]?\d[\d.,]*)([$€元块]|[a-z]{3})?")
_DASH = str.maketrans("\u2212\u2013\u2014", "---")  # minus, en and em dash
# "- 5": a lone sign before the amount joins it.
_SIGN = re.compile(r"(?<!\S)([+-])\s+(?=\d)")
_TIME = re.compile(r"\d{1,2}:\d{2}|\b\d{1,2}\s*(am|pm|a\.m|p\.m)\b|\ba las\b")
# Words that mean a date, a question, an edit or a calendar action: LLM.
_SKIP = frozenset(
    "hoy manana ayer anteayer pasado lunes martes miercoles jueves viernes "
    "sabado domingo semana mes cuanto cuanta que cual como cuando donde "
    "resumen presupuesto ultimo ultima era cambia cambiar corrige corregir "
    "edita editar anula anular borra borrar deshaz deshacer cancela cancelar "
    "recuerda recuerdame recordar recordatorio cita reunion evento agenda "
    "today tomorrow yesterday monday tuesday wednesday thursday friday saturday "
    "sunday week month how what which when where summary budget last change "
    "edit fix undo delete remove cancel remind reminder meeting event "
    "appointment calendar schedule".split()
)
# Chinese dates, questions, edits and calendar words, matched inside a word.
_SKIP_ZH = (
    "今天 明天 昨天 后天 前天 星期 礼拜 周 月 多少 什么 哪 怎么 吗 提醒 会议 "
    "开会 日程 预约 取消 修改 删除 撤销 预算 总结 上一"
).split()
_INGRESO = frozenset({"ingreso", "income", "收入"})
_GASTO = frozenset({"gasto", "gaste", "expense", "spent", "支出", "花了"})
_STRIP = _INGRESO | _GASTO
_LEAD = frozenset({"en", "de", "por", "para", "on", "for", "at"})
_KEYWORDS = {
    "restaurantes": "cafe almuerzo desayuno cena restaurante coffee lunch "
    "breakfast dinner restaurant 咖啡 午饭 午餐 早饭 早餐 晚饭 晚餐 饭店 餐厅 外卖",
    "transporte": "uber taxi bus gasolina gas fuel metro 打车 出租车 公交 地铁 "
    "加油 滴滴",
    "supermercado": "mercado super groceries grocery supermarket 超市 菜 买菜",
    "suscripciones": "netflix spotify subscription 会员 订阅",
    "vivienda": "arriendo rent 房租 租金",
    "servicios": "luz agua internet celular electricity water phone 电费 水费 "
    "话费 网费",
    "salud": "farmacia medico pharmacy doctor medicine 药 医院 看病",
    "entretenimiento": "cine movie movies cinema 电影",
    "compras": "ropa clothes shopping 衣服 购物",
}
_CATEGORIA = {w: cat for cat, words in _KEYWORDS.items() for w in words.split()}
_CATEGORIA_ZH = [(w, cat) for w, cat in _CATEGORIA.items() if not w.isascii()]


def _categoria(palabra: str) -> str | None:
    """Exact match, else a Chinese keyword inside the word."""
    exacta = _CATEGORIA.get(palabra)
    if exacta or palabra.isascii():
        return exacta
    return next((cat for w, cat in _CATEGORIA_ZH if w in palabra), None)


# "editar: ..." in each language; a category by its key or any shown name.
EDITAR = frozenset({"editar", "edit", "修改"})
MAX_WORDS = 8  # ponytail: longer messages are prose; let the LLM read them
NOT_POSITIVE = "El monto debe ser mayor que 0."


@dataclass(frozen=True)
class Entry:
    tipo: str  # gasto | ingreso | "" (bare amount: ask)
    monto: Decimal
    moneda: str
    nota: str
    categoria: str  # gastos only; "" for ingresos
    error: str | None = None


def norm(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text.lower().translate(_DASH))
    return "".join(c for c in decomposed if not unicodedata.combining(c))


_CAT_NOMBRES = {
    norm(nombre): clave
    for clave in CATEGORIES
    for nombre in (clave, *CATEGORIAS[clave].values())
}
# Note words typed without their accent, stored with it ("cafe" -> "café").
_ACENTOS = {
    norm(w): w
    for w in "café médico crédito débito teléfono película películas música "
    "cafetería panadería autobús avión".split()
}


def number(raw: str) -> Decimal | None:
    """``2``, ``2,5``, ``2.000`` (thousands), ``1.234,56``, ``1,234.56``."""
    sign = -1 if raw.startswith("-") else 1
    s = raw.lstrip("+-")
    if not re.fullmatch(r"\d+(?:[.,]\d+)*", s):
        return None
    seps = [c for c in s if c in ".,"]
    if len(set(seps)) == 2:
        dec = seps[-1]
        whole, frac = s.rsplit(dec, 1)
        if dec in whole or not re.fullmatch(r"\d{1,3}(?:[.,]\d{3})+", whole):
            return None
        s = re.sub(r"[.,]", "", whole) + "." + frac
    elif len(seps) > 1:
        if not re.fullmatch(r"\d{1,3}(?:[.,]\d{3})+", s):
            return None
        s = re.sub(r"[.,]", "", s)
    elif seps:
        whole, frac = s.split(seps[0])
        s = whole + ("" if len(frac) == 3 else ".") + frac
    return sign * Decimal(s)


def _amount(tok: str) -> tuple[Decimal, str | None] | None:
    """An amount token with its attached currency, if any."""
    m = _TOKEN.fullmatch(tok)
    if not m:
        return None
    sym = m[1] or m[3]
    if sym and sym not in _CUR:
        return None  # 2abc: unknown code glued to the number
    value = number(m[2])
    return None if value is None else (value, _CUR[sym] if sym else None)


def amount(text: str) -> tuple[Decimal, str | None] | None:
    """``3usd``, ``2000 cop``, ``usd 2``, ``$3`` or ``3``: for /editar."""
    toks = norm(text).split()
    code = None
    if len(toks) == 2 and toks[1] in _CUR:
        code = toks.pop()
    elif len(toks) == 2 and toks[0] in _CUR:
        code = toks.pop(0)
    found = _amount(toks[0]) if len(toks) == 1 else None
    if found is None or (code and found[1]):
        return None
    return found[0], found[1] or (_CUR[code] if code else None)


def correccion(text: str) -> dict | None:
    """``editar: 15 cop · almuerzo · restaurantes`` -> the fields to change in
    the last movement ({} when nothing is recognized); None if not a correction.

    Amount (and currency), category by name in any language, and the other
    words as the note, in any order.
    """
    head, sep, rest = text.replace("：", ":").partition(":")
    if not sep or norm(head.strip()) not in EDITAR:
        return None
    campos: dict = {}
    nota = []
    for raw in re.split(r"[\s/·;]+", rest.strip()):
        tok = norm(raw)
        found = _amount(tok) if tok else None
        if not tok:
            continue
        if found and "monto" not in campos:
            campos["monto"] = abs(found[0])
            if found[1]:
                campos["moneda"] = found[1]
        elif tok in _CUR:
            campos["moneda"] = _CUR[tok]
        elif tok in _CAT_NOMBRES:
            campos["categoria"] = _CAT_NOMBRES[tok]
        else:
            nota.append(raw)
    if nota:
        campos["nota"] = " ".join(nota)
    return campos


def parse(text: str, default: str = "USD") -> Entry | None:
    raw = _SIGN.sub(r"\1", text.translate(_DASH)).split()  # "– 5" as "-5"
    toks = [norm(t).strip(".,;:!") for t in raw]
    joined = " ".join(toks)
    if (
        not raw
        or len(raw) > MAX_WORDS
        or text.lstrip().startswith("/")
        or "?" in text
        or "¿" in text
        or "？" in text
        or _TIME.search(joined)
        or _SKIP.intersection(toks)
        or any(w in joined for w in _SKIP_ZH)
    ):
        return None
    amounts = [i for i, t in enumerate(toks) if _amount(t)]
    digits = [i for i, t in enumerate(toks) if any(c.isdigit() for c in t)]
    if len(amounts) != 1 or digits != amounts:
        return None
    i = amounts[0]
    value, moneda = _amount(toks[i]) or (Decimal(0), None)
    signo = toks[i][:1] if toks[i][:1] in "+-" else ""
    value = abs(value)
    used = {i}
    if moneda is None:
        for j in (i + 1, i - 1):
            if 0 <= j < len(toks) and toks[j] in _CUR:
                moneda, used = _CUR[toks[j]], {i, j}
                break
    if _INGRESO.intersection(toks) or signo == "+":
        tipo = "ingreso"
    elif _GASTO.intersection(toks) or signo == "-":
        tipo = "gasto"
    else:
        tipo = "gasto"  # words without a type: an expense
    words = [
        (raw[k].strip(".,;:!"), toks[k])
        for k in range(len(raw))
        if k not in used and toks[k] not in _STRIP and toks[k]
    ]
    if words and words[0][1] in _LEAD:
        words = words[1:]
    decidido = signo or _STRIP.intersection(toks)
    if not words and not decidido:
        tipo = ""  # a bare amount: gasto or ingreso is the user's call
    nota = " ".join(_ACENTOS.get(w.lower(), w) for w, _ in words)
    categoria = ""
    if tipo != "ingreso":
        found = (_categoria(n) for _, n in words)
        categoria = next((c for c in found if c), "otros")
    return Entry(
        tipo=tipo,
        monto=value,
        moneda=moneda or default,
        nota=nota,
        categoria=categoria,
        error=None if value > 0 else NOT_POSITIVE,
    )
