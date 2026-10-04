"""Per-turn trace: one structured log line.

Cloud Logging keeps it, and the log-based metrics in ``infra/monitoring.tf``
turn its fields (cost, latency, tokens, rejected calls) into Cloud Monitoring
series that the alerts and the local Grafana dashboard read.

No PII: no chat_id, no message text (only its sha256), no reply.
"""

from __future__ import annotations

import hashlib
import json
import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from assistant.llm.client import TurnResult

log = logging.getLogger(__name__)


def record_turn(result: TurnResult, latency_ms: int, text: str) -> None:
    """Never raises."""
    try:
        fields: dict[str, Any] = {
            "prompt_version": result.prompt_version,
            "model": result.model,
            "tools": list(result.tools),
            "latency_ms": int(latency_ms),
            "tokens_hit": result.tokens_hit,
            "tokens_miss": result.tokens_miss,
            "tokens_out": result.tokens_out,
            "cost_usd": float(result.cost_usd),
            "rejected": result.rejected,
            "text_sha256": hashlib.sha256(text.encode()).hexdigest(),
        }
        log.info(json.dumps({"event": "llm_turn", **fields}))
    except Exception as exc:  # observability must never break a turn
        log.error(json.dumps({"event": "trace_error", "code": type(exc).__name__}))
