"""Agent graph orchestrator: Extractor → Diff → Risk/Guidance → Qs+Writer."""

from __future__ import annotations

import json
import time
import uuid
from collections.abc import AsyncIterator
from typing import Any

from backend.app.agents import diff_normalizer, extractor, questions_writer, risk_guidance
from backend.app.agents.common import AgentContext
from backend.app.llm.base import get_llm_provider
from backend.app.metrics.collector import estimate_cost_usd, get_metrics_collector
from backend.app.rag.store import get_rag_store
from backend.app.schemas import AnalystPacket, JobRequest, Mode
from backend.app.slo import latency_budget_ms, should_degrade


def _sse(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


async def run_packet(req: JobRequest) -> AnalystPacket:
    """Build a full analyst packet (non-streaming)."""
    packet: AnalystPacket | None = None
    async for event, data in _run(req):
        if event == "packet":
            packet = AnalystPacket.model_validate(data)
    assert packet is not None
    return packet


async def stream_packet(req: JobRequest) -> AsyncIterator[str]:
    """SSE event generator for /v1/packet/stream."""
    async for event, data in _run(req):
        yield _sse(event, data)


async def _run(req: JobRequest) -> AsyncIterator[tuple[str, dict[str, Any]]]:
    trace_id = str(uuid.uuid4())
    t0 = time.perf_counter()
    ttft_ms: float | None = None
    budget = latency_budget_ms(req.mode, req.latency_budget_ms)
    llm = get_llm_provider()
    rag = get_rag_store()

    ctx = AgentContext(
        current_text=req.current_text,
        prior_text=req.prior_text,
        ticker=req.ticker,
        mode=req.mode,
        llm=llm,
        rag_snippets=rag.lookup(req.ticker) if req.ticker else [],
    )

    agents_run: list[str] = []
    degraded = False
    degrade_reasons: list[str] = []

    def elapsed_ms() -> float:
        return (time.perf_counter() - t0) * 1000

    def mark_ttft() -> None:
        nonlocal ttft_ms
        if ttft_ms is None:
            ttft_ms = elapsed_ms()

    def merge_degrade(remaining: list[str]) -> list[str]:
        nonlocal degraded
        do_deg, skip = should_degrade(elapsed_ms(), budget, remaining)
        if not do_deg:
            return []
        degraded = True
        # Rebuild official reasons from slo helper semantics
        if "questions_writer" in skip and elapsed_ms() >= budget * 0.7:
            reason = f"latency_budget: skip questions_writer at {elapsed_ms():.0f}ms / {budget}ms"
            if reason not in degrade_reasons:
                degrade_reasons.append(reason)
        if elapsed_ms() >= budget:
            reason = f"latency_budget_exceeded: {elapsed_ms():.0f}ms >= {budget}ms"
            if reason not in degrade_reasons:
                degrade_reasons.append(reason)
        return skip

    # --- Extractor ---
    yield ("status", {"trace_id": trace_id, "agent": "extractor", "state": "start", "mode": req.mode.value})
    await extractor.run(ctx)
    if not ctx.rag_snippets and ctx.ticker:
        ctx.rag_snippets = rag.lookup(ctx.ticker)
        ctx.extracted["rag"] = ctx.rag_snippets
    agents_run.append("extractor")
    mark_ttft()
    yield (
        "agent",
        {
            "trace_id": trace_id,
            "agent": "extractor",
            "state": "done",
            "metrics_found": len(ctx.extracted.get("current_metrics", [])),
            "ticker": ctx.ticker,
            "rag_hits": len(ctx.rag_snippets),
        },
    )

    remaining = ["diff_normalizer", "risk_guidance", "questions_writer"]
    skip = merge_degrade(remaining)

    # --- Diff ---
    if "diff_normalizer" in skip:
        degraded = True
        reason = "skipped diff_normalizer due to latency budget"
        if reason not in degrade_reasons:
            degrade_reasons.append(reason)
    else:
        yield ("status", {"trace_id": trace_id, "agent": "diff_normalizer", "state": "start"})
        await diff_normalizer.run(ctx)
        agents_run.append("diff_normalizer")
        yield (
            "agent",
            {
                "trace_id": trace_id,
                "agent": "diff_normalizer",
                "state": "done",
                "diff_count": len(ctx.diffs),
            },
        )

    remaining = ["risk_guidance", "questions_writer"]
    skip = merge_degrade(remaining)

    # --- Risk / Guidance ---
    if "risk_guidance" in skip:
        degraded = True
        reason = "skipped risk_guidance due to latency budget"
        if reason not in degrade_reasons:
            degrade_reasons.append(reason)
    else:
        yield ("status", {"trace_id": trace_id, "agent": "risk_guidance", "state": "start"})
        await risk_guidance.run(ctx)
        agents_run.append("risk_guidance")
        yield (
            "agent",
            {
                "trace_id": trace_id,
                "agent": "risk_guidance",
                "state": "done",
                "guidance": len(ctx.guidance),
                "risks": len(ctx.risks),
            },
        )

    remaining = ["questions_writer"]
    skip = merge_degrade(remaining)

    # Fast mode: shallow questions by design (not an SLO degrade).
    # Thorough + budget pressure: degrade and skip deep Qs.
    budget_skip_qs = "questions_writer" in skip
    deep = req.mode == Mode.thorough and not budget_skip_qs

    yield (
        "status",
        {
            "trace_id": trace_id,
            "agent": "questions_writer",
            "state": "start",
            "deep": deep,
        },
    )
    await questions_writer.run(ctx, deep=deep)
    if budget_skip_qs:
        agents_run.append("questions_writer_degraded")
        yield (
            "agent",
            {
                "trace_id": trace_id,
                "agent": "questions_writer",
                "state": "degraded",
                "deep": False,
                "questions": len(ctx.questions),
            },
        )
    else:
        agents_run.append("questions_writer")
        yield (
            "agent",
            {
                "trace_id": trace_id,
                "agent": "questions_writer",
                "state": "done",
                "deep": deep,
                "questions": len(ctx.questions),
            },
        )

    e2e_ms = elapsed_ms()
    if e2e_ms >= budget:
        degraded = True
        reason = f"latency_budget_exceeded: {e2e_ms:.0f}ms >= {budget}ms"
        if reason not in degrade_reasons:
            degrade_reasons.append(reason)

    cost = estimate_cost_usd(ctx.input_tokens, ctx.output_tokens)
    packet = AnalystPacket(
        ticker=ctx.ticker,
        mode=req.mode,
        summary=ctx.summary,
        diffs=ctx.diffs,
        guidance=ctx.guidance,
        risks=ctx.risks,
        questions=ctx.questions,
        degraded=degraded,
        degrade_reasons=degrade_reasons,
        trace_id=trace_id,
        agents_run=agents_run,
    )

    get_metrics_collector().record(
        trace_id=trace_id,
        mode=req.mode.value,
        e2e_ms=e2e_ms,
        ttft_ms=ttft_ms,
        input_tokens=ctx.input_tokens,
        output_tokens=ctx.output_tokens,
        cost_usd=cost,
        degraded=degraded,
    )

    yield (
        "metrics",
        {
            "trace_id": trace_id,
            "e2e_ms": round(e2e_ms, 2),
            "ttft_ms": round(ttft_ms, 2) if ttft_ms is not None else None,
            "input_tokens": ctx.input_tokens,
            "output_tokens": ctx.output_tokens,
            "cost_usd": round(cost, 8),
            "degraded": degraded,
            "budget_ms": budget,
        },
    )
    yield ("packet", packet.model_dump(mode="json"))
    yield ("done", {"trace_id": trace_id})
