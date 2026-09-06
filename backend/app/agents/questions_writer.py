"""Questions + Writer agent — Street Qs and narrative summary."""

from __future__ import annotations

from backend.app.agents.common import AgentContext
from backend.app.schemas import Severity, StreetQuestion


async def run(ctx: AgentContext, *, deep: bool = True) -> None:
    questions: list[StreetQuestion] = []
    critical = [d for d in ctx.diffs if d.severity == Severity.critical]
    watch = [d for d in ctx.diffs if d.severity == Severity.watch]
    added_risks = [r for r in ctx.risks if r.change_type == "added"]
    raised = [g for g in ctx.guidance if g.change_type == "raised"]

    def q(question: str, rationale: str, citations=None) -> None:
        questions.append(StreetQuestion(question=question, rationale=rationale, citations=citations or []))

    if critical:
        d = critical[0]
        q(
            f"What drove the move in {d.label} from {d.prior_value} to {d.current_value}?",
            f"{d.label} ranked critical in the quarter-over-quarter diff.",
            d.citations,
        )
    if any(d.label == "GAAP EPS" for d in ctx.diffs) and any(d.label == "Non-GAAP EPS" for d in ctx.diffs):
        gaap = next(d for d in ctx.diffs if d.label == "GAAP EPS")
        ngaap = next(d for d in ctx.diffs if d.label == "Non-GAAP EPS")
        q(
            "Why did GAAP and non-GAAP EPS diverge this quarter?",
            f"GAAP {gaap.prior_value}→{gaap.current_value}; non-GAAP {ngaap.prior_value}→{ngaap.current_value}. "
            f"Note: {ngaap.gaap_note or 'see exclusions'}.",
            gaap.citations + ngaap.citations,
        )
    if raised:
        g = raised[0]
        q(
            f"How durable is the {g.topic.lower()} raise, and what visibility supports it?",
            "Guidance language was raised versus the prior quarter.",
            g.citations,
        )
    for r in added_risks[:2]:
        q(
            f"How should investors underwrite the new risk around {r.theme.lower()}?",
            "New risk language appeared in the current release.",
            r.citations,
        )
    if ctx.rag_snippets:
        q(
            f"How does this print compare with known {ctx.ticker or 'ticker'} context (segment mix / themes)?",
            "Ticker context RAG snippets were available for enrichment.",
            [],
        )

    if deep:
        llm = await ctx.llm.complete(
            "questions for the Street based on earnings diff\n" + "\n".join(f"- {x.question}" for x in questions),
            system="You are a sell-side associate drafting follow-ups.",
            fast=False,
        )
        ctx.input_tokens += llm.input_tokens
        ctx.output_tokens += llm.output_tokens
        # Keep structured questions; LLM text is for token/cost realism.
    else:
        questions = questions[:2]
        llm = await ctx.llm.complete("short summary only", fast=True)
        ctx.input_tokens += llm.input_tokens
        ctx.output_tokens += llm.output_tokens

    ticker = ctx.ticker or "the company"
    n_crit = len(critical)
    n_risk = len(added_risks)
    ctx.summary = (
        f"{ticker} printed a quarter with {len(ctx.diffs)} tracked metric deltas "
        f"({n_crit} critical). Guidance shifts: {len(ctx.guidance)}. "
        f"New or hardened risks: {n_risk}. "
        + ("Thorough packet includes Street questions." if deep else "Fast mode returned a partial question set.")
    )
    if watch and not critical:
        ctx.summary += f" Watch items include {', '.join(d.label for d in watch[:3])}."

    ctx.questions = questions
