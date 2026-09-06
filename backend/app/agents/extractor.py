"""Extractor agent — pull metrics, guidance, and risk spans."""

from __future__ import annotations

from backend.app.agents.common import AgentContext, extract_ticker, parse_metrics, section_block


async def run(ctx: AgentContext) -> None:
    current_metrics = parse_metrics(ctx.current_text, "current")
    prior_metrics = parse_metrics(ctx.prior_text or "", "prior") if ctx.prior_text else []
    guidance_cur = section_block(ctx.current_text, "Guidance") or section_block(ctx.current_text, "Outlook")
    guidance_prior = ""
    if ctx.prior_text:
        guidance_prior = section_block(ctx.prior_text, "Guidance") or section_block(ctx.prior_text, "Outlook")
    risk_cur = section_block(ctx.current_text, "Risk Factors") or section_block(ctx.current_text, "Risks")
    risk_prior = ""
    if ctx.prior_text:
        risk_prior = section_block(ctx.prior_text, "Risk Factors") or section_block(ctx.prior_text, "Risks")

    if not ctx.ticker:
        ctx.ticker = extract_ticker(ctx.current_text)

    llm = await ctx.llm.complete(
        f"Extract key earnings facts for {ctx.ticker or 'UNKNOWN'}. Metrics found: {[m['label'] for m in current_metrics]}",
        system="You are an equity research extractor.",
        fast=ctx.mode.value == "fast",
    )
    ctx.input_tokens += llm.input_tokens
    ctx.output_tokens += llm.output_tokens

    ctx.extracted = {
        "current_metrics": current_metrics,
        "prior_metrics": prior_metrics,
        "guidance_current": guidance_cur,
        "guidance_prior": guidance_prior,
        "risk_current": risk_cur,
        "risk_prior": risk_prior,
        "rag": ctx.rag_snippets,
    }
