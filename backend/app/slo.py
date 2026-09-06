"""SLO targets and degrade decisions."""

from __future__ import annotations

import os

from backend.app.schemas import Mode


def latency_budget_ms(mode: Mode, override: int | None = None) -> int:
    if override is not None and override > 0:
        return override
    if mode == Mode.fast:
        return int(os.getenv("FAST_LATENCY_BUDGET_MS", "8000"))
    return int(os.getenv("THOROUGH_LATENCY_BUDGET_MS", "30000"))


def should_degrade(elapsed_ms: float, budget_ms: int, remaining_agents: list[str]) -> tuple[bool, list[str]]:
    """Return whether to degrade and which agents to skip."""
    reasons: list[str] = []
    skip: list[str] = []
    if elapsed_ms >= budget_ms * 0.7 and "questions_writer" in remaining_agents:
        skip.append("questions_writer")
        reasons.append(f"latency_budget: skip questions_writer at {elapsed_ms:.0f}ms / {budget_ms}ms")
    if elapsed_ms >= budget_ms and remaining_agents:
        for agent in remaining_agents:
            if agent not in skip:
                skip.append(agent)
        reasons.append(f"latency_budget_exceeded: {elapsed_ms:.0f}ms >= {budget_ms}ms")
    return bool(skip), skip
