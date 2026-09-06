"""Risk & Guidance agent — language shift detection."""

from __future__ import annotations

import re

from backend.app.agents.common import AgentContext, find_span
from backend.app.schemas import GuidanceShift, RiskItem, Severity


def _sentences(block: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+", block.strip())
    return [p.strip() for p in parts if len(p.strip()) > 20]


def _guidance_change(prior: str, current: str) -> GuidanceShift | None:
    if not current and not prior:
        return None
    change = "added"
    severity = Severity.watch
    topic = "Forward outlook"
    cur_l = current.lower()
    prior_l = prior.lower()
    if ("high-single" in cur_l and "mid-single" in prior_l) or (
        "high-single" in cur_l and "mid-single" in cur_l and "versus prior" in cur_l
    ):
        change = "raised"
        topic = "Full-year growth"
        severity = Severity.critical
    elif "mid-single" in cur_l and "high-single" in prior_l:
        change = "lowered"
        topic = "Full-year growth"
        severity = Severity.critical
    elif "limited" in cur_l and "constructive" in prior_l:
        change = "softened"
        topic = "Demand commentary"
        severity = Severity.watch
    elif prior and current and current != prior:
        change = "hardened" if len(current) > len(prior) * 1.1 else "softened"
    citations = []
    if current:
        c = find_span(current if False else current, current[:80] if len(current) > 80 else current, "current")
        # Prefer locating in full doc via caller; store quote from section
        from backend.app.schemas import SpanCitation

        citations.append(SpanCitation(doc="current", start=0, end=min(len(current), 120), quote=current[:120]))
    if prior:
        from backend.app.schemas import SpanCitation

        citations.append(SpanCitation(doc="prior", start=0, end=min(len(prior), 120), quote=prior[:120]))
    return GuidanceShift(
        topic=topic,
        prior_language=prior or None,
        current_language=current or None,
        change_type=change,  # type: ignore[arg-type]
        severity=severity,
        citations=citations,
    )


_RISK_KEYWORDS = [
    ("restructuring", "Go-to-market restructuring", "added", Severity.critical),
    ("competitive pricing", "Competitive pricing", "added", Severity.watch),
    ("cybersecurity", "Cybersecurity costs", "added", Severity.watch),
    ("export-control", "Export controls", "unchanged", Severity.watch),
    ("customer concentration", "Customer concentration", "unchanged", Severity.info),
    ("public-sector", "Public-sector budgets", "added", Severity.watch),
    ("inference accelerators", "Inference competition", "added", Severity.watch),
    ("design-win", "Design-win slippage", "added", Severity.watch),
]


async def run(ctx: AgentContext) -> None:
    g_cur = ctx.extracted.get("guidance_current", "")
    g_prior = ctx.extracted.get("guidance_prior", "")
    r_cur = ctx.extracted.get("risk_current", "")
    r_prior = ctx.extracted.get("risk_prior", "")

    guidance: list[GuidanceShift] = []
    g = _guidance_change(g_prior, g_cur)
    if g:
        # Re-cite against full documents when possible
        citations = []
        if g_cur:
            span = find_span(ctx.current_text, g_cur[:60], "current")
            if span:
                citations.append(span)
        if g_prior and ctx.prior_text:
            span = find_span(ctx.prior_text, g_prior[:60], "prior")
            if span:
                citations.append(span)
        if citations:
            g.citations = citations
        guidance.append(g)

    risks: list[RiskItem] = []
    cur_l = r_cur.lower()
    prior_l = r_prior.lower()
    for keyword, theme, default_change, severity in _RISK_KEYWORDS:
        in_cur = keyword in cur_l
        in_prior = keyword in prior_l
        if not in_cur and not in_prior:
            continue
        if in_cur and not in_prior:
            change = "added"
            sev = severity
        elif in_prior and not in_cur:
            change = "removed"
            sev = Severity.info
        else:
            change = "unchanged"
            sev = Severity.info
        citations = []
        if in_cur:
            span = find_span(ctx.current_text, keyword, "current")
            if span:
                citations.append(span)
        if in_prior and ctx.prior_text:
            span = find_span(ctx.prior_text, keyword, "prior")
            if span:
                citations.append(span)
        risks.append(
            RiskItem(
                theme=theme,
                prior_language=next((s for s in _sentences(r_prior) if keyword in s.lower()), None),
                current_language=next((s for s in _sentences(r_cur) if keyword in s.lower()), None),
                change_type=change,  # type: ignore[arg-type]
                severity=sev if change != "unchanged" else Severity.info,
                citations=citations,
            )
        )

    ctx.guidance = guidance
    ctx.risks = risks

    llm = await ctx.llm.complete(
        f"Assess {len(guidance)} guidance shifts and {len(risks)} risk items",
        fast=ctx.mode.value == "fast",
    )
    ctx.input_tokens += llm.input_tokens
    ctx.output_tokens += llm.output_tokens
