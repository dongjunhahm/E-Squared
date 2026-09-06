"""Deterministic mock LLM for demos without GPU."""

from __future__ import annotations

from backend.app.llm.base import LLMProvider, LLMResult


class MockProvider(LLMProvider):
    async def complete(self, prompt: str, *, system: str | None = None, fast: bool = False) -> LLMResult:
        # Agents use heuristics; mock returns a short acknowledgment for token accounting.
        text = "mock-ok"
        if "questions" in prompt.lower():
            text = (
                "1. Why did GAAP EPS decline while non-GAAP rose?\n"
                "2. How durable is the raised full-year growth outlook?\n"
                "3. What is the near-term impact of the Americas restructuring?"
            )
        approx_in = max(1, len(prompt) // 4)
        approx_out = max(1, len(text) // 4)
        model = "mock-fast" if fast else "mock-thorough"
        return LLMResult(text=text, input_tokens=approx_in, output_tokens=approx_out, model=model)
