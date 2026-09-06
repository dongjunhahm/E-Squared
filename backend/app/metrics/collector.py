"""SQLite metrics collector for TTFT / e2e / tokens / cost."""

from __future__ import annotations

import os
import sqlite3
import statistics
from pathlib import Path

from backend.app.schemas import MetricsSummary


def _percentile(values: list[float], p: float) -> float | None:
    if not values:
        return None
    if len(values) == 1:
        return float(values[0])
    ordered = sorted(values)
    k = (len(ordered) - 1) * (p / 100.0)
    f = int(k)
    c = min(f + 1, len(ordered) - 1)
    if f == c:
        return float(ordered[f])
    return float(ordered[f] + (ordered[c] - ordered[f]) * (k - f))


class MetricsCollector:
    def __init__(self, db_path: str | None = None) -> None:
        self.db_path = db_path or os.getenv("METRICS_DB_PATH", "data/metrics.db")
        if self.db_path != ":memory:":
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                trace_id TEXT NOT NULL,
                mode TEXT,
                e2e_ms REAL,
                ttft_ms REAL,
                input_tokens INTEGER,
                output_tokens INTEGER,
                cost_usd REAL,
                degraded INTEGER,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        self._conn.commit()

    def record(
        self,
        *,
        trace_id: str,
        mode: str,
        e2e_ms: float,
        ttft_ms: float | None,
        input_tokens: int,
        output_tokens: int,
        cost_usd: float,
        degraded: bool,
    ) -> None:
        self._conn.execute(
            """
            INSERT INTO runs(trace_id, mode, e2e_ms, ttft_ms, input_tokens, output_tokens, cost_usd, degraded)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                trace_id,
                mode,
                e2e_ms,
                ttft_ms,
                input_tokens,
                output_tokens,
                cost_usd,
                1 if degraded else 0,
            ),
        )
        self._conn.commit()

    def summary(self) -> MetricsSummary:
        rows = self._conn.execute(
            "SELECT e2e_ms, ttft_ms, cost_usd, degraded FROM runs"
        ).fetchall()
        if not rows:
            return MetricsSummary()
        e2e = [float(r[0]) for r in rows if r[0] is not None]
        ttft = [float(r[1]) for r in rows if r[1] is not None]
        costs = [float(r[2]) for r in rows if r[2] is not None]
        degrade_count = sum(1 for r in rows if r[3])
        run_count = len(rows)
        return MetricsSummary(
            run_count=run_count,
            degrade_count=degrade_count,
            degrade_rate=(degrade_count / run_count) if run_count else 0.0,
            p50_e2e_ms=_percentile(e2e, 50),
            p95_e2e_ms=_percentile(e2e, 95),
            p50_ttft_ms=_percentile(ttft, 50),
            p95_ttft_ms=_percentile(ttft, 95),
            avg_cost_usd=(statistics.mean(costs) if costs else None),
            total_cost_usd=sum(costs) if costs else 0.0,
        )


_collector: MetricsCollector | None = None


def get_metrics_collector() -> MetricsCollector:
    global _collector
    if _collector is None:
        _collector = MetricsCollector()
    return _collector


def estimate_cost_usd(input_tokens: int, output_tokens: int) -> float:
    in_rate = float(os.getenv("USD_PER_1K_INPUT", "0.0001"))
    out_rate = float(os.getenv("USD_PER_1K_OUTPUT", "0.0002"))
    return (input_tokens / 1000.0) * in_rate + (output_tokens / 1000.0) * out_rate
