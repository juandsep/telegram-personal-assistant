import dataclasses
import hashlib
import json
import logging
import re
from decimal import Decimal

from assistant.llm.client import TurnResult
from assistant.observability import trace

TEXT = "gasté 45 en almuerzo con Ana"  # must never appear in logs
RESULT = TurnResult(
    reply="✓ 45 USD → restaurantes",
    keyboard=None,
    messages=[],
    tools=["registrar_gasto"],
    prompt_version="abc",
    model="deepseek-flash",
    tokens_hit=100,
    tokens_miss=10,
    tokens_out=5,
    cost_usd=Decimal("0.0000096"),
    rejected=0,
)


def test_logs_one_json_line_without_pii(caplog) -> None:
    with caplog.at_level(logging.INFO, logger=trace.__name__):
        trace.record_turn(RESULT, 812, TEXT)
    [record] = caplog.records
    line = json.loads(record.getMessage())
    assert line["event"] == "llm_turn"
    assert line["text_sha256"] == hashlib.sha256(TEXT.encode()).hexdigest()
    assert line["latency_ms"] == 812 and line["tokens_hit"] == 100
    assert "chat_id" not in line and "reply" not in line
    assert "Ana" not in record.getMessage() and "45" not in record.getMessage()


def test_line_matches_the_log_based_metrics(caplog) -> None:
    # The same REGEXP_EXTRACT patterns as infra/monitoring.tf: if the line
    # format changes, the Cloud Monitoring series silently go empty.
    with caplog.at_level(logging.INFO, logger=trace.__name__):
        trace.record_turn(dataclasses.replace(RESULT, rejected=2), 812, TEXT)
    msg = caplog.records[0].getMessage()
    for field, value in (
        ("cost_usd", 9.6e-6),
        ("latency_ms", 812),
        ("tokens_out", 5),
        ("rejected", 2),
    ):
        match = re.search(rf'"{field}": ([-0-9.eE+]+)', msg)
        assert match and float(match[1]) == value
    version = re.search(r'"prompt_version": "([0-9a-f]+)"', msg)
    assert version and version[1] == "abc"


def test_failure_never_raises(caplog) -> None:
    broken = dataclasses.replace(RESULT, cost_usd=object())  # type: ignore[arg-type]
    with caplog.at_level(logging.INFO, logger=trace.__name__):
        trace.record_turn(broken, 5, TEXT)
    assert json.loads(caplog.records[-1].getMessage()) == {
        "event": "trace_error",
        "code": "TypeError",
    }
    assert all("Ana" not in r.getMessage() for r in caplog.records)
