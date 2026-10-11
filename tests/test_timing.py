import logging

from assistant.observability import timing


def test_only_slow_calls_are_logged(monkeypatch, caplog) -> None:
    caplog.set_level(logging.WARNING)
    ticks = iter([0.0, 0.1, 10.0, 11.5])
    monkeypatch.setattr(timing.time, "monotonic", lambda: next(ticks))
    with timing.timed("fast"):
        pass
    with timing.timed("telegram.sendMessage"):
        pass
    assert [r.getMessage() for r in caplog.records] == [
        "slow_call name=telegram.sendMessage ms=1500"
    ]
