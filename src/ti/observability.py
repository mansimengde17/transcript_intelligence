"""Lightweight trace and cost telemetry with no vendor lock-in."""

from __future__ import annotations

import json
import threading
import time
import uuid
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator


@dataclass
class Span:
    trace_id: str
    span_id: str
    name: str
    started_at: str
    duration_ms: float
    status: str
    attributes: dict[str, Any]


class CostEstimator:
    """Configurable token-price registry used for budget regression tests."""

    def __init__(self, prices_per_million: dict[str, tuple[float, float]] | None = None):
        self.prices = prices_per_million or {"deterministic": (0.0, 0.0)}

    def estimate(self, model: str, input_tokens: int, output_tokens: int) -> float:
        input_price, output_price = self.prices.get(model, (0.0, 0.0))
        return round((input_tokens * input_price + output_tokens * output_price) / 1_000_000, 8)


class TraceRecorder:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    @contextmanager
    def span(self, name: str, trace_id: str | None = None, **attributes: Any) -> Iterator[dict[str, Any]]:
        trace_id = trace_id or uuid.uuid4().hex
        span_id = uuid.uuid4().hex[:16]
        started = time.perf_counter()
        mutable = dict(attributes)
        status = "ok"
        try:
            yield mutable
        except Exception as exc:
            status = "error"
            mutable["error.type"] = type(exc).__name__
            mutable["error.message"] = str(exc)[:500]
            raise
        finally:
            record = Span(
                trace_id=trace_id,
                span_id=span_id,
                name=name,
                started_at=datetime.now(timezone.utc).isoformat(),
                duration_ms=round((time.perf_counter() - started) * 1000, 3),
                status=status,
                attributes=mutable,
            )
            with self._lock, self.path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(asdict(record), sort_keys=True) + "\n")
