"""Pydantic schemas for Earnings Diff → Analyst Packet."""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class Mode(str, Enum):
    fast = "fast"
    thorough = "thorough"


class Severity(str, Enum):
    info = "info"
    watch = "watch"
    critical = "critical"


class SpanCitation(BaseModel):
    doc: Literal["current", "prior", "context"]
    start: int = Field(ge=0)
    end: int = Field(ge=0)
    quote: str


class DiffItem(BaseModel):
    label: str
    prior_value: str | None = None
    current_value: str | None = None
    unit: str | None = None
    gaap_note: str | None = None
    severity: Severity = Severity.info
    citations: list[SpanCitation] = Field(default_factory=list)


class GuidanceShift(BaseModel):
    topic: str
    prior_language: str | None = None
    current_language: str | None = None
    change_type: Literal["raised", "lowered", "narrowed", "widened", "added", "removed", "softened", "hardened"]
    severity: Severity = Severity.watch
    citations: list[SpanCitation] = Field(default_factory=list)


class RiskItem(BaseModel):
    theme: str
    prior_language: str | None = None
    current_language: str | None = None
    change_type: Literal["added", "removed", "softened", "hardened", "unchanged"]
    severity: Severity = Severity.watch
    citations: list[SpanCitation] = Field(default_factory=list)


class StreetQuestion(BaseModel):
    question: str
    rationale: str
    citations: list[SpanCitation] = Field(default_factory=list)


class AnalystPacket(BaseModel):
    ticker: str | None = None
    mode: Mode
    summary: str
    diffs: list[DiffItem] = Field(default_factory=list)
    guidance: list[GuidanceShift] = Field(default_factory=list)
    risks: list[RiskItem] = Field(default_factory=list)
    questions: list[StreetQuestion] = Field(default_factory=list)
    degraded: bool = False
    degrade_reasons: list[str] = Field(default_factory=list)
    trace_id: str
    agents_run: list[str] = Field(default_factory=list)


class JobRequest(BaseModel):
    current_text: str = Field(min_length=1)
    prior_text: str | None = None
    ticker: str | None = None
    mode: Mode = Mode.thorough
    latency_budget_ms: int | None = None


class MetricsSummary(BaseModel):
    run_count: int = 0
    degrade_count: int = 0
    degrade_rate: float = 0.0
    p50_e2e_ms: float | None = None
    p95_e2e_ms: float | None = None
    p50_ttft_ms: float | None = None
    p95_ttft_ms: float | None = None
    avg_cost_usd: float | None = None
    total_cost_usd: float = 0.0


class HealthResponse(BaseModel):
    status: str = "ok"
    service: str = "earnings-diff"
    llm_provider: str
