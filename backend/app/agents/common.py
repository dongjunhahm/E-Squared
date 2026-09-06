"""Shared agent context helpers."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from backend.app.llm.base import LLMProvider
from backend.app.schemas import Mode, SpanCitation


@dataclass
class AgentContext:
    current_text: str
    prior_text: str | None
    ticker: str | None
    mode: Mode
    llm: LLMProvider
    rag_snippets: list[str] = field(default_factory=list)
    extracted: dict = field(default_factory=dict)
    diffs: list = field(default_factory=list)
    guidance: list = field(default_factory=list)
    risks: list = field(default_factory=list)
    questions: list = field(default_factory=list)
    summary: str = ""
    input_tokens: int = 0
    output_tokens: int = 0


def find_span(text: str, needle: str, doc: str = "current") -> SpanCitation | None:
    idx = text.lower().find(needle.lower())
    if idx < 0:
        return None
    end = idx + len(needle)
    return SpanCitation(doc=doc, start=idx, end=end, quote=text[idx:end])  # type: ignore[arg-type]


def extract_ticker(text: str) -> str | None:
    m = re.search(r"\(([A-Z]+):\s*([A-Z.]+)\)", text)
    if m:
        return m.group(2)
    m = re.search(r"\b([A-Z]{2,5})\b\s+today reported", text)
    return m.group(1) if m else None


_METRIC_PATTERNS = [
    ("Revenue", re.compile(r"Revenue:\s*\$?([\d,.]+)\s*(million|billion)?", re.I), "$"),
    ("GAAP EPS", re.compile(r"GAAP(?:\s+diluted)?\s+EPS:\s*\$?([\d.]+)", re.I), "$"),
    ("Non-GAAP EPS", re.compile(r"Non-GAAP(?:\s+diluted)?\s+EPS:\s*\$?([\d.]+)", re.I), "$"),
    ("Gross margin", re.compile(r"Gross margin:\s*([\d.]+)%", re.I), "%"),
    ("Operating cash flow", re.compile(r"Operating cash flow:\s*\$?([\d,.]+)\s*(million|billion)?", re.I), "$"),
    ("R&D % revenue", re.compile(r"R&D as % of revenue:\s*([\d.]+)%", re.I), "%"),
]


def parse_metrics(text: str, doc: str) -> list[dict]:
    out: list[dict] = []
    for label, pattern, unit in _METRIC_PATTERNS:
        m = pattern.search(text)
        if not m:
            continue
        value = m.group(1).replace(",", "")
        scale = ""
        if m.lastindex and m.lastindex >= 2 and m.group(2):
            scale = m.group(2)
        display = f"{value}{(' ' + scale) if scale else ''}"
        cite = find_span(text, m.group(0), doc=doc)
        out.append(
            {
                "label": label,
                "value": display,
                "raw": float(value),
                "unit": unit,
                "scale": scale,
                "gaap_note": _gaap_note(label, text),
                "citation": cite,
            }
        )
    return out


def _gaap_note(label: str, text: str) -> str | None:
    if "Non-GAAP" in label:
        m = re.search(r"Non-GAAP[^\n]*\(([^)]+)\)", text, re.I)
        return m.group(1).strip() if m else "Non-GAAP excludes adjustments disclosed in release"
    if label == "GAAP EPS":
        return "GAAP as reported"
    return None


def section_block(text: str, header: str) -> str:
    # Match a whole-line section header (avoid "prior guidance" mid-sentence).
    pattern = re.compile(
        rf"(?m)^[ \t]*{re.escape(header)}[ \t]*\n(.*?)(?=\n[ \t]*[A-Z][A-Za-z0-9 &/-]{{2,}}[ \t]*\n|\Z)",
        re.S | re.I,
    )
    m = pattern.search(text)
    return m.group(1).strip() if m else ""
