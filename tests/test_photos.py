import json
from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import httpx
import pytest
import respx
from firestore_fake import FakeDB

from assistant.context import ToolContext
from assistant.services import photos, state

TZ = "America/Bogota"
CTX = ToolContext(
    chat_id="42",
    role="owner",
    currency="COP",
    timezone=TZ,
    update_id=1,
    now=datetime(2026, 10, 7, 20, tzinfo=ZoneInfo(TZ)),
    lang="es",
)
URL = photos.GEMINI_URL.format(model="m")


@pytest.fixture
def db(monkeypatch: pytest.MonkeyPatch) -> FakeDB:
    fake = FakeDB()
    monkeypatch.setattr(state, "_db", lambda: fake)
    return fake


def test_equal_split_numbers_the_others() -> None:
    assert photos.split(Decimal("200000"), 4, []) == [
        ("👤1", Decimal("50000")),
        ("👤2", Decimal("50000")),
        ("👤3", Decimal("50000")),
    ]


def test_items_by_name_scale_tax_and_share_the_rest() -> None:
    items = [
        {"name": "pizza", "price": "40", "person": "Ana"},
        {"name": "pasta", "price": "30", "person": "yo"},
        {"name": "vino", "price": "30", "person": ""},
    ]
    # 110 total = 100 of items + 10% tip; vino shared by Ana, me and one more.
    shares = photos.split(Decimal("110.00"), 3, items)
    assert shares == [("Ana", Decimal("55.00")), ("👤1", Decimal("11.00"))]


def test_named_people_raise_the_count() -> None:
    items = [
        {"name": "a", "price": "10", "person": "Ana"},
        {"name": "b", "price": "10", "person": "Luis"},
    ]
    names = [n for n, _ in photos.split(Decimal("30"), 0, items)]
    assert names == ["Ana", "Luis"]


def test_analyze_parses_gemini_json(db: FakeDB) -> None:
    photos.add_meal(CTX, {"name": "Arepa", "kcal": 300, "protein_g": 8})
    body = {"candidates": [{"content": {"parts": [{"text": '{"kind": "other"}'}]}}]}
    with respx.mock:
        route = respx.post(URL).mock(return_value=httpx.Response(200, json=body))
        assert photos.analyze(b"jpg", "cena 4", CTX, "k", "m") == {"kind": "other"}
    assert route.calls[0].request.headers["x-goog-api-key"] == "k"
    sent = json.loads(route.calls[0].request.read())
    prompt = sent["contents"][0]["parts"][1]["text"]
    assert "(300 kcal, protein 8 g, carbs 0 g, fat 0 g)" in prompt  # the day so far
    schema = sent["generationConfig"]["responseSchema"]
    assert {"health", "tip"} <= set(schema["required"])


@pytest.mark.parametrize("response", [httpx.Response(500), httpx.Response(200)])
def test_analyze_failures_are_unavailable(db: FakeDB, response: httpx.Response) -> None:
    with respx.mock:
        respx.post(URL).mock(return_value=response)
        with pytest.raises(photos.PhotoUnavailable):
            photos.analyze(b"jpg", "", CTX, "k", "m")


def test_analyze_without_key_is_unavailable() -> None:
    with pytest.raises(photos.PhotoUnavailable):
        photos.analyze(b"jpg", "", CTX, "", "m")


def test_meals_add_up_today_and_delete(db: FakeDB) -> None:
    first = photos.add_meal(CTX, {"name": "Arepa", "kcal": 300})
    photos.add_meal(CTX, {"name": "Café", "kcal": 50})
    assert photos.kcal_today(CTX) == 350
    photos.delete_meal("42", first)
    assert photos.kcal_today(CTX) == 50


def test_split_closes_when_everyone_paid(db: FakeDB) -> None:
    debtors = [("Ana", Decimal("10")), ("👤1", Decimal("10"))]
    split_id = photos.save_split(CTX, "Cena", Decimal("30"), "COP", debtors)
    assert [i for i, _ in photos.open_splits("42")] == [split_id]
    assert photos.mark_paid("42", split_id, 0)["abierta"] is True
    assert photos.mark_paid("42", split_id, 1)["abierta"] is False
    assert photos.open_splits("42") == []
    assert photos.mark_paid("42", "missing", 0) is None


def test_misread_thousands_are_scaled_for_currencies_without_cents() -> None:
    data = {"total": 168.3, "currency": "COP", "items": [{"price": 42.0}]}
    assert photos._thousands(data) == {
        "total": "168300.0",
        "currency": "COP",
        "items": [{"price": "42000.0"}],
    }
    usd = {"total": 16.83, "currency": "USD", "items": []}
    assert photos._thousands(dict(usd)) == usd
