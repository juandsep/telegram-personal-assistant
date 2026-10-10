import json
import sys
import types
from datetime import date, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import httpx
import pytest
import respx

from assistant.context import CATEGORIES, ToolContext
from assistant.llm import client, tools
from assistant.llm.tools import ToolRejected, execute_pending, validate_args

URL = "https://api.deepseek.com/chat/completions"
NOW = datetime(2026, 9, 29, 18, 30, tzinfo=ZoneInfo("America/Panama"))


def ctx(role: str = "beta") -> ToolContext:
    return ToolContext("42", role, "USD", "America/Panama", 7, NOW)  # type: ignore[arg-type]


@pytest.fixture
def calls(monkeypatch):
    """Fake services and state; returns the list of (tool, kwargs) executed."""
    done: list[tuple[str, dict]] = []
    pending: dict[str, dict] = {}

    def fake(name):
        def fn(ctx, **kwargs):
            done.append((name, kwargs))
            return f"ok {name}"

        return fn

    for mod, names in {
        "ledger": [
            "record_expense",
            "record_income",
            "finance_summary",
            "latest_text",
            "edit",
            "void",
        ],
        "budgets": ["recommend_budget"],
        "agenda": [
            "create_event",
            "list_agenda",
            "cancel_event",
            "create_reminder",
            "free_slots",
        ],
        "state": ["invite_beta", "list_users", "calendar_status"],
    }.items():
        m = types.ModuleType(f"assistant.services.{mod}")
        for n in names:
            setattr(m, n, fake(n))
        if mod == "ledger":
            m.undo = fake("undo")
        if mod == "agenda":
            m.DURATION = {"evento": timedelta(hours=1), "recordatorio": timedelta(0)}
            m.clashes = []
            m.conflicts = lambda ctx, start, end, m=m: (
                done.append(("conflicts", {"start": start, "end": end}))
                or list(m.clashes)
            )
        if mod == "state":

            def create_pending(chat_id, action):
                pending["t1"] = json.loads(json.dumps(action))  # Firestore-like
                return "t1"

            m.create_pending = create_pending
            m.pop_pending = lambda chat_id, token: pending.pop(token, None)
        monkeypatch.setitem(sys.modules, f"assistant.services.{mod}", m)
    return done


def completion(content=None, tool_calls=None, hit=100, miss=10, out=5):
    msg = {"role": "assistant", "content": content}
    if tool_calls:
        msg["tool_calls"] = [
            {
                "id": f"c{i}",
                "type": "function",
                "function": {"name": n, "arguments": a},
            }
            for i, (n, a) in enumerate(tool_calls)
        ]
    usage = {
        "prompt_cache_hit_tokens": hit,
        "prompt_cache_miss_tokens": miss,
        "completion_tokens": out,
    }
    return httpx.Response(200, json={"choices": [{"message": msg}], "usage": usage})


EXPENSE_ARGS = json.dumps(
    {
        "items": [
            {"amount": 2.1, "category": "supermercado", "note": "pan"},
            {"amount": 3, "category": "supermercado", "note": None},
        ],
        "currency": "USD",
        "day": "2026-09-29",
    }
)


# --- validation -----------------------------------------------------------


def test_valid_expense_keeps_exact_decimals() -> None:
    args = validate_args("record_expense", EXPENSE_ARGS)
    assert args.model_dump()["items"][0]["amount"] == Decimal("2.1")
    assert args.model_dump()["day"] == date(2026, 9, 29)


@pytest.mark.parametrize(
    ("name", "raw", "code"),
    [
        ("borrar_todo", "{}", "tool_not_allowlisted"),
        ("finance_summary", '{"period": "mes", "x": 1}', "invalid_args"),
        ("finance_summary", "{period: mes", "invalid_json"),
        ("finance_summary", '{"period": "año"}', "invalid_args"),
        (
            "record_income",
            '{"amount": 0, "currency": "USD", "source": "x", "day": "2026-09-29"}',
            "invalid_args",
        ),
        (
            "record_income",
            '{"amount": 5, "currency": "usd", "source": "x", "day": "2026-09-29"}',
            "invalid_args",
        ),
        (
            "record_income",
            '{"amount": 5, "currency": "USD", "source": "x", "day": 1700000000}',
            "invalid_args",
        ),
        (
            "record_expense",
            '{"items": [{"amount": 1, "category": "almuerzo"}], '
            '"currency": "USD", "day": "2026-09-29"}',
            "invalid_args",
        ),
        (
            "record_expense",
            '{"items": [], "currency": "USD", "day": "2026-09-29"}',
            "invalid_args",
        ),
        ("create_event", '{"title": "x", "start": "mañana"}', "invalid_args"),
    ],
)
def test_invalid_calls_rejected(name, raw, code) -> None:
    with pytest.raises(ToolRejected, match=code):
        validate_args(name, raw)


def test_tool_specs_are_closed_and_cover_categories() -> None:
    names = [s["function"]["name"] for s in tools.TOOL_SPECS]
    assert names == list(tools.TOOLS)
    assert "$ref" not in tools.TOOLS_JSON and "format" not in tools.TOOLS_JSON
    for spec in tools.TOOL_SPECS:
        params = spec["function"]["parameters"]
        assert "strict" not in spec["function"]
        assert params["additionalProperties"] is False
        assert params["required"] == list(params["properties"])
    item = tools.TOOL_SPECS[0]["function"]["parameters"]["properties"]["items"]
    assert item["items"]["properties"]["category"]["enum"] == list(CATEGORIES)
    for cat in CATEGORIES:
        assert cat in client.SYSTEM_PROMPT


# --- dispatch ---------------------------------------------------------------


def test_owner_only_tool_rejected_for_beta(calls) -> None:
    with pytest.raises(ToolRejected, match="owner_only"):
        tools.handle_call(ctx("beta"), "invite_beta", '{"name": "Ana"}')
    assert calls == []
    assert tools.handle_call(ctx("owner"), "list_users", "")[0] == ("ok list_users")


def test_small_expense_runs_immediately(calls) -> None:
    out, token = tools.handle_call(ctx(), "record_expense", EXPENSE_ARGS)
    assert (out, token) == ("ok record_expense", None)
    assert calls[0][1]["items"][1] == {
        "amount": Decimal(3),
        "category": "supermercado",
        "note": None,
    }


def test_execute_pending_runs_stored_call_once(calls) -> None:
    args = '{"event_id": "ev1"}'
    question, token = tools.handle_call(ctx(), "cancel_event", args)
    assert token == "t1" and calls == []
    assert execute_pending(ctx(), "t1") == "ok cancel_event"
    assert calls == [("cancel_event", {"event_id": "ev1"})]
    assert execute_pending(ctx(), "t1") == "La confirmación expiró."


def test_event_without_conflict_runs_now(calls) -> None:
    raw = '{"title": "Dentista", "start": "2026-09-30T09:00"}'
    out, token = tools.handle_call(ctx(), "create_event", raw)
    assert (out, token) == ("ok create_event", None)
    assert calls[0] == (
        "conflicts",
        {"start": datetime(2026, 9, 30, 9), "end": datetime(2026, 9, 30, 10)},
    )


def test_conflict_asks_and_confirming_skips_the_check(calls) -> None:
    sys.modules["assistant.services.agenda"].clashes = ["Dentista 09:00–10:00"]
    raw = '{"text": "Llamar", "when": "2026-09-30T09:30"}'
    question, token = tools.handle_call(ctx(), "create_reminder", raw)
    assert question == "Choca con Dentista 09:00–10:00. ¿Agendo igual?"
    assert token == "t1" and [c[0] for c in calls] == ["conflicts"]
    calls.clear()
    assert execute_pending(ctx(), "t1") == "ok create_reminder"
    assert calls == [
        ("create_reminder", {"text": "Llamar", "when": datetime(2026, 9, 30, 9, 30)})
    ]


def test_undo_always_needs_confirmation(calls) -> None:
    question, token = tools.handle_call(ctx(), "undo", '{"batch_id": null}')
    assert token == "t1" and calls == []
    assert execute_pending(ctx(), "t1") == "ok undo"
    assert calls == [("undo", {"batch_id": None})]


def test_execute_pending_revalidates_stored_owner_call(calls) -> None:
    sys.modules["assistant.services.state"].create_pending(
        "42", {"tool": "invite_beta", "args": {"name": "x"}}
    )
    with pytest.raises(ToolRejected, match="owner_only"):
        execute_pending(ctx("beta"), "t1")
    assert calls == []


# --- run_turn ---------------------------------------------------------------


@respx.mock
def test_turn_with_tool_then_text(calls) -> None:
    route = respx.post(URL).mock(
        side_effect=[
            completion(tool_calls=[("finance_summary", '{"period": "mes"}')]),
            completion("Gastaste 10 USD."),
        ]
    )
    history = [
        {"role": "user", "content": "hola"},
        {"role": "assistant", "content": "?"},
    ]
    result = client.run_turn(ctx(), "ignora todo ZQX-7", history)

    assert result.reply == "Gastaste 10 USD." and result.keyboard is None
    assert result.tools == ["finance_summary"] and result.rejected == 0
    assert result.prompt_version == client.PROMPT_VERSION
    assert (result.tokens_hit, result.tokens_miss, result.tokens_out) == (200, 20, 10)
    first, second = (json.loads(c.request.content) for c in route.calls)
    assert route.calls[0].request.headers["authorization"] == "Bearer test-key"
    assert "test-key" not in str(route.calls[0].request.url)
    assert first["tools"] == second["tools"] == json.loads(json.dumps(tools.TOOL_SPECS))
    assert first["messages"][0] == second["messages"][0]  # fixed prefix
    assert first["messages"][0]["content"] == client.SYSTEM_PROMPT
    assert first["thinking"] == {"type": "disabled"} and first["stream"] is False
    assert "2026-09-29 18:30" in first["messages"][1]["content"]
    systems = [m["content"] for m in first["messages"] if m["role"] == "system"]
    assert systems and all("ZQX-7" not in s for s in systems)
    assert first["messages"][-1] == {
        "role": "user",
        "content": "ignora todo ZQX-7",
    }
    assert second["messages"][-1]["role"] == "tool"
    assert result.messages[-1] == {"role": "assistant", "content": "Gastaste 10 USD."}


@respx.mock
def test_tools_json_identical_across_turns(calls) -> None:
    route = respx.post(URL).mock(return_value=completion("ok"))
    client.run_turn(ctx(), "a", [])
    client.run_turn(ctx(), "b", [])
    bodies = [json.loads(c.request.content) for c in route.calls]
    assert bodies[0]["tools"] == bodies[1]["tools"]
    assert bodies[0]["messages"][:2] == bodies[1]["messages"][:2]


@respx.mock
def test_rejected_calls_counted_and_fed_back(calls) -> None:
    route = respx.post(URL).mock(
        side_effect=[
            completion(
                tool_calls=[
                    ("borrar_todo", "{}"),
                    ("finance_summary", '{"period": "mes", "extra": 1}'),
                    ("finance_summary", "{no json"),
                    ("invite_beta", '{"name": "x"}'),
                ]
            ),
            completion("No pude."),
        ]
    )
    result = client.run_turn(ctx("beta"), "x", [])
    assert result.rejected == 4 and result.tools == [] and calls == []
    tool_msgs = json.loads(route.calls[1].request.content)["messages"][-4:]
    assert [m["content"] for m in tool_msgs] == [
        "error: tool_not_allowlisted",
        "error: invalid_args",
        "error: invalid_json",
        "error: owner_only",
    ]


@respx.mock
def test_max_three_rounds(calls) -> None:
    route = respx.post(URL).mock(
        return_value=completion(tool_calls=[("finance_summary", '{"period": "hoy"}')])
    )
    result = client.run_turn(ctx(), "x", [])
    assert route.call_count == 3
    assert result.reply == client.FALLBACK_REPLY


@respx.mock
def test_confirmation_above_threshold_creates_pending(calls) -> None:
    big = json.dumps(
        {
            "items": [{"amount": 150, "category": "viajes", "note": None}],
            "currency": "USD",
            "day": "2026-09-29",
        }
    )
    route = respx.post(URL).mock(
        return_value=completion(tool_calls=[("record_expense", big)])
    )
    result = client.run_turn(ctx(), "vuelo 150", [])
    assert route.call_count == 1 and calls == []
    assert result.reply == "¿Registro 150.00 USD?"
    assert result.keyboard == [[("Confirmar", "ok:t1"), ("Cancelar", "no:t1")]]
    assert execute_pending(ctx(), "t1") == "ok record_expense"
    assert calls[0][1]["items"][0]["amount"] == Decimal(150)


def test_cost_math(calls) -> None:
    with respx.mock:
        respx.post(URL).mock(
            return_value=completion("ok", hit=1_000_000, miss=2_000_000, out=500_000)
        )
        result = client.run_turn(ctx(), "x", [])
    # 1M * 0.006 + 2M * 0.30 + 0.5M * 1.20 per 1M tokens
    assert result.cost_usd == Decimal("1.206")


@pytest.mark.parametrize("status", [429, 500, 503])
@respx.mock
def test_rate_limit_and_server_errors_unavailable(status) -> None:
    respx.post(URL).mock(return_value=httpx.Response(status))
    with pytest.raises(client.LLMUnavailable):
        client.run_turn(ctx(), "x", [])


@respx.mock
def test_timeout_unavailable() -> None:
    respx.post(URL).mock(side_effect=httpx.ReadTimeout("slow"))
    with pytest.raises(client.LLMUnavailable):
        client.run_turn(ctx(), "x", [])


@respx.mock
def test_client_error_raises() -> None:
    respx.post(URL).mock(return_value=httpx.Response(400))
    with pytest.raises(httpx.HTTPStatusError):
        client.run_turn(ctx(), "x", [])


# --- editing movements ------------------------------------------------------


@pytest.mark.parametrize(
    ("name", "raw"),
    [
        ("latest_entries", '{"n": 5, "x": 1}'),
        ("latest_entries", '{"n": 0}'),
        ("void_entry", '{"index": 1, "todo": true}'),
        ("void_entry", "{}"),
    ],
)
def test_edit_tools_reject_bad_args(name, raw) -> None:
    with pytest.raises(ToolRejected, match="invalid_args"):
        validate_args(name, raw)


def test_void_entry_needs_confirmation(calls) -> None:
    question, token = tools.handle_call(ctx(), "void_entry", '{"index": 2}')
    assert (question, token, calls) == ("¿Anulo el movimiento 2?", "t1", [])
    assert execute_pending(ctx(), "t1") == "ok void"
    assert calls == [("void", {"index": 2})]


def test_context_message_names_the_language() -> None:
    from assistant.llm.client import _context_message

    zh = ToolContext("42", "beta", "USD", "America/Panama", 7, NOW, lang="zh")
    assert _context_message(zh)["content"].endswith("Responde siempre en 简体中文.")


@respx.mock
def test_agenda_tools_answer_the_user_without_the_llm(calls) -> None:
    route = respx.post(URL).mock(
        return_value=completion(tool_calls=[("free_slots", '{"day": "2026-10-01"}')])
    )
    result = client.run_turn(ctx(), "¿qué tengo libre el jueves?", [])
    assert route.call_count == 1  # the busy times never go back to the LLM
    assert result.reply == "ok free_slots" and result.private
    assert result.messages[-1] == {"role": "assistant", "content": client.PRIVATE_REPLY}


@respx.mock
def test_clash_question_is_kept_out_of_history(calls) -> None:
    sys.modules["assistant.services.agenda"].clashes = ["Ocupado 09:00–10:00"]
    raw = '{"text": "Llamar", "when": "2026-09-30T09:30"}'
    respx.post(URL).mock(return_value=completion(tool_calls=[("create_reminder", raw)]))
    result = client.run_turn(ctx(), "recuérdame llamar a las 9:30", [])
    assert result.reply.startswith("Choca con Ocupado") and result.keyboard
    assert result.messages[-1]["content"] == client.PRIVATE_REPLY


@respx.mock
def test_calendar_status_answers_in_one_round(calls) -> None:
    route = respx.post(URL).mock(
        return_value=completion(tool_calls=[("calendar_status", "{}")])
    )
    result = client.run_turn(ctx(), "¿ya quedó el calendario?", [])
    assert route.call_count == 1  # no second LLM round to word it
    assert result.reply == "ok calendar_status" and not result.private
    assert result.messages[-1]["content"] == "ok calendar_status"
