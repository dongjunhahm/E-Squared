# Earnings Diff → Analyst Packet (AgentOps Lite)

Turn two earnings releases into a structured **analyst packet**: metric diffs, guidance/risk language shifts, Street questions, span citations, and live SLO metrics.

## Architecture

```
POST /v1/packet[/stream]
        │
        ▼
   Orchestrator (SLO budget)
        │
        ├─ Extractor      → metrics, guidance/risk spans (+ ticker RAG)
        ├─ Diff/Normalizer→ QoQ deltas + severity (GAAP vs non-GAAP notes)
        ├─ Risk/Guidance  → language shifts (raised / added / softened…)
        └─ Questions+Writer → Street Qs + narrative (shallow in Fast mode)
        │
        ▼
   AnalystPacket JSON  +  MetricsCollector (SQLite)
```

- **LLM**: `LLM_PROVIDER=mock` by default (deterministic, no GPU). Optional `ollama`.
- **RAG**: tiny SQLite seed for `ACME` / `NXLB` context snippets.
- **SLO**: Fast ~8s / Thorough ~30s budgets; near-budget skips deep questions and marks `degraded`.

## Quick start

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # optional

uvicorn backend.app.main:app --host 0.0.0.0 --port 43125
```

Open http://127.0.0.1:43125 — load ACME or NXLB samples, stream a packet, check metrics.

### API

| Method | Path | Notes |
|--------|------|-------|
| GET | `/health` | Provider + status |
| POST | `/v1/packet` | Sync `AnalystPacket` |
| POST | `/v1/packet/stream` | SSE: `status` / `agent` / `metrics` / `packet` / `done` |
| GET | `/v1/metrics/summary` | p50/p95 e2e & TTFT, degrade rate, $ |

Example:

```bash
curl -s http://127.0.0.1:43125/health
curl -s -X POST http://127.0.0.1:43125/v1/packet \
  -H 'Content-Type: application/json' \
  -d "{\"current_text\":\"$(cat data/samples/acme_q2_2026.txt | sed 's/\"/\\\\\"/g')\",\"prior_text\":\"$(cat data/samples/acme_q1_2026.txt | sed 's/\"/\\\\\"/g')\",\"ticker\":\"ACME\",\"mode\":\"thorough\"}"
```

## Demo script (interview)

1. **Health** — `GET /health` shows `llm_provider=mock`.
2. **ACME thorough** — Load ACME Q1→Q2. Point out GAAP EPS **critical** decline vs Non-GAAP rise, raised full-year growth, new Americas restructuring risk, citations on diffs.
3. **Stream** — Watch agent events in the log (`extractor` → `diff_normalizer` → `risk_guidance` → `questions_writer`).
4. **Fast mode** — Same inputs, fewer / shallower Street questions; still returns a usable packet.
5. **Metrics** — Refresh dashboard: run count, p50/p95 e2e, degrade rate, estimated $.
6. **Degrade (optional)** — `latency_budget_ms: 1` forces skip path and `degraded=true`.
7. **NXLB** — Second ticker proves RAG seed + different risk themes (inference / design-win).

## Tests & golden eval

```bash
pytest -q
python scripts/eval_golden.py
```

Golden fixtures live in `tests/golden/` and assert labels, GAAP severity, guidance raise, and risk themes.

## Interview talking points

- **AgentOps over a single prompt**: staged graph with clear contracts (`AnalystPacket` schema), not a black-box essay.
- **Evidence**: span citations (`doc` / `start` / `end` / `quote`) keep claims grounded in the release text.
- **Product realism**: Fast vs Thorough + latency budget degrade — demo what production agents do under SLO pressure.
- **Observability**: TTFT, e2e latency percentiles, token/$ estimates, degrade rate in SQLite — ops loop without a heavy stack.
- **Swap-ready LLM**: mock for CI/demo; Ollama adapter when a local model is available.

## Layout

```
backend/app/
  agents/          extractor, diff_normalizer, risk_guidance, questions_writer
  llm/             mock + ollama
  rag/store.py     ACME/NXLB context seed
  metrics/         SQLite collector + summary
  orchestrator.py  graph + SSE
  main.py          FastAPI
frontend/index.html
data/samples/      ACME + NXLB Q1/Q2 releases
scripts/eval_golden.py
tests/
```
