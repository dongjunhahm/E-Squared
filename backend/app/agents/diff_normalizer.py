"""Diff / Normalizer agent — align metrics and rank severity."""

from __future__ import annotations

from backend.app.agents.common import AgentContext
from backend.app.schemas import DiffItem, Severity


def _severity(label: str, prior: float | None, current: float | None) -> Severity:
    if prior is None or current is None:
        return Severity.info
    if prior == 0:
        return Severity.watch
    delta_pct = abs((current - prior) / abs(prior)) * 100
    # EPS GAAP down while revenue up is especially interesting
    if label == "GAAP EPS" and current < prior:
        return Severity.critical if delta_pct >= 5 else Severity.watch
    if label == "Gross margin" and current < prior and delta_pct >= 2:
        return Severity.critical
    if delta_pct >= 8:
        return Severity.watch
    return Severity.info


async def run(ctx: AgentContext) -> None:
    cur = {m["label"]: m for m in ctx.extracted.get("current_metrics", [])}
    prior = {m["label"]: m for m in ctx.extracted.get("prior_metrics", [])}
    labels = list(dict.fromkeys([*prior.keys(), *cur.keys()]))
    diffs: list[DiffItem] = []
    for label in labels:
        c = cur.get(label)
        p = prior.get(label)
        citations = []
        if c and c.get("citation"):
            citations.append(c["citation"])
        if p and p.get("citation"):
            citations.append(p["citation"])
        severity = _severity(label, p["raw"] if p else None, c["raw"] if c else None)
        gaap_note = (c or p or {}).get("gaap_note")
        diffs.append(
            DiffItem(
                label=label,
                prior_value=p["value"] if p else None,
                current_value=c["value"] if c else None,
                unit=(c or p or {}).get("unit"),
                gaap_note=gaap_note,
                severity=severity,
                citations=citations,
            )
        )
    ctx.diffs = diffs

    llm = await ctx.llm.complete(
        f"Normalize {len(diffs)} metric diffs for mode={ctx.mode.value}",
        fast=True,
    )
    ctx.input_tokens += llm.input_tokens
    ctx.output_tokens += llm.output_tokens
