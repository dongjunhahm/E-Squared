#!/usr/bin/env python3
"""Golden eval: run sample packets and check structural expectations."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.app.orchestrator import run_packet  # noqa: E402
from backend.app.schemas import JobRequest, Mode  # noqa: E402


async def eval_fixture(path: Path) -> list[str]:
    fixture = json.loads(path.read_text())
    prior = (ROOT / fixture["prior_file"]).read_text()
    current = (ROOT / fixture["current_file"]).read_text()
    expect = fixture["expect"]
    packet = await run_packet(
        JobRequest(
            current_text=current,
            prior_text=prior,
            ticker=fixture.get("ticker"),
            mode=Mode.thorough,
        )
    )
    errors: list[str] = []
    if len(packet.diffs) < expect.get("min_diffs", 0):
        errors.append(f"diffs {len(packet.diffs)} < {expect['min_diffs']}")
    labels = {d.label for d in packet.diffs}
    for label in expect.get("must_have_labels", []):
        if label not in labels:
            errors.append(f"missing label {label}")
    sev = expect.get("gaap_eps_severity")
    if sev:
        gaap = next((d for d in packet.diffs if d.label == "GAAP EPS"), None)
        if gaap is None:
            errors.append("missing GAAP EPS diff")
        elif gaap.severity.value != sev:
            errors.append(f"GAAP EPS severity {gaap.severity.value} != {sev}")
    wanted = set(expect.get("guidance_change_types", []))
    if wanted:
        got = {g.change_type for g in packet.guidance}
        if not wanted & got:
            errors.append(f"guidance types {got} missing any of {wanted}")
    themes = set(expect.get("risk_themes_any", []))
    if themes:
        got = {r.theme for r in packet.risks}
        if not themes & got:
            errors.append(f"risk themes {got} missing any of {themes}")
    min_q = expect.get("min_questions_thorough", 0)
    if len(packet.questions) < min_q:
        errors.append(f"questions {len(packet.questions)} < {min_q}")
    return errors


async def main() -> int:
    parser = argparse.ArgumentParser(description="Run golden packet evals")
    parser.add_argument(
        "--fixtures",
        type=Path,
        default=ROOT / "tests" / "golden",
        help="Directory of golden JSON fixtures",
    )
    args = parser.parse_args()
    fixtures = sorted(args.fixtures.glob("*.json"))
    if not fixtures:
        print("No fixtures found", file=sys.stderr)
        return 2
    failed = 0
    for path in fixtures:
        errors = await eval_fixture(path)
        if errors:
            failed += 1
            print(f"FAIL {path.name}:")
            for e in errors:
                print(f"  - {e}")
        else:
            print(f"PASS {path.name}")
    print(f"{len(fixtures) - failed}/{len(fixtures)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
