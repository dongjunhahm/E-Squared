"""Tiny SQLite / in-memory ticker context store for ACME + NXLB."""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

_SEED: dict[str, list[str]] = {
    "ACME": [
        "ACME segment mix historically ~55% enterprise software / ~45% infrastructure.",
        "Prior filings flagged Americas go-to-market productivity as a watch item for 2026.",
        "Street models often bridge GAAP vs non-GAAP EPS via SBC, amortization, and one-time charges.",
        "AI infrastructure attach and renewals have been the main upside narrative in recent prints.",
    ],
    "NXLB": [
        "NXLB sells accelerators and related IP into hyperscale and OEM design-wins.",
        "Gross margin is sensitive to mix between training vs inference silicon and wafer costs.",
        "Export-control and wafer allocation have been recurring risk themes in sell-side notes.",
        "Design-win qualification slips commonly push revenue recognition into later periods.",
    ],
}


class RagStore:
    def __init__(self, db_path: str | None = None) -> None:
        self.db_path = db_path or os.getenv("RAG_DB_PATH", "data/rag.db")
        if self.db_path != ":memory:":
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS ticker_context (
                ticker TEXT NOT NULL,
                snippet TEXT NOT NULL,
                UNIQUE(ticker, snippet)
            )
            """
        )
        self._conn.commit()
        self._seed()

    def _seed(self) -> None:
        for ticker, snippets in _SEED.items():
            for snippet in snippets:
                self._conn.execute(
                    "INSERT OR IGNORE INTO ticker_context(ticker, snippet) VALUES (?, ?)",
                    (ticker.upper(), snippet),
                )
        self._conn.commit()

    def lookup(self, ticker: str | None, limit: int = 4) -> list[str]:
        if not ticker:
            return []
        rows = self._conn.execute(
            "SELECT snippet FROM ticker_context WHERE ticker = ? LIMIT ?",
            (ticker.upper().strip(), limit),
        ).fetchall()
        return [r[0] for r in rows]


_store: RagStore | None = None


def get_rag_store() -> RagStore:
    global _store
    if _store is None:
        _store = RagStore()
    return _store
