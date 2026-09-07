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

- **LLM**: `LLM_PROVIDER=mock` | `ollama` | `api` (see below). Default `mock` needs no GPU/key.
- **SQLite**: metrics runs → `METRICS_DB_PATH=data/metrics.db`; ticker RAG → `RAG_DB_PATH=data/rag.db`.
- **RAG**: tiny SQLite seed for `ACME` / `NXLB` context snippets.
- **SLO**: Fast ~8s / Thorough ~30s budgets; near-budget skips deep questions and marks `degraded`.

## Quick start

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # then paste API_KEY if using LLM_PROVIDER=api (.env is gitignored)

uvicorn backend.app.main:app --host 0.0.0.0 --port 43125
```

Open http://127.0.0.1:43125 — load ACME or NXLB samples, stream a packet, check metrics.

## LLM providers (`mock` | `ollama` | `api`)

Set `LLM_PROVIDER` in `.env` (copied from `.env.example`):

| Value | When to use | Required env |
|-------|-------------|--------------|
| `mock` | CI, demos, no GPU/key (default) | none |
| `ollama` | Local models via Ollama | `OLLAMA_BASE_URL`, `OLLAMA_MODEL`, `OLLAMA_MODEL_FAST` |
| `api` | OpenAI-compatible chat completions (OpenAI, Cursor, other gateways) | `API_KEY` (paste your key), `API_BASE_URL` (default `https://api.openai.com/v1`), `API_MODEL`, `API_MODEL_FAST` |

**Switch examples**

```bash
# Deterministic local demo
LLM_PROVIDER=mock

# Local Ollama
LLM_PROVIDER=ollama
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_MODEL=llama3.2
OLLAMA_MODEL_FAST=llama3.2:1b

# OpenAI-compatible API (paste key; never commit .env)
LLM_PROVIDER=api
API_KEY=sk-...
API_BASE_URL=https://api.openai.com/v1
API_MODEL=gpt-4o-mini
API_MODEL_FAST=gpt-4o-mini
```

`api` calls `POST {API_BASE_URL}/chat/completions` with `Authorization: Bearer {API_KEY}`. Point `API_BASE_URL` at any OpenAI-compatible endpoint. `CURSOR_API_KEY` is accepted as a fallback when `API_KEY` is unset.

> **Note on Cursor keys:** a Cursor API key (`crsr_…`) is **not** an OpenAI key and there is no public Cursor OpenAI-compatible `/chat/completions` gateway — it only works with the Cursor Cloud Agents API. For `LLM_PROVIDER=api` use a real OpenAI-compatible key + `API_BASE_URL` (OpenAI `sk-…`, Groq/Together/DeepSeek/LLM-Gateway, or a local Ollama `…/v1`). Use `LLM_PROVIDER=mock` for a deterministic, key-free demo.

### API

| Method | Path | Notes |
|--------|------|-------|
| GET | `/health` | Provider + status |
| POST | `/v1/packet` | Sync `AnalystPacket` (JSON body) |
| POST | `/v1/packet/upload` | Sync `AnalystPacket` from **file upload** (multipart: `current_file`, optional `prior_file`, `ticker`, `mode`, `latency_budget_ms`) |
| POST | `/v1/packet/stream` | SSE: `status` / `agent` / `metrics` / `packet` / `done` (JSON body) |
| POST | `/v1/packet/stream/upload` | SSE stream from **file upload** (same multipart fields as `/v1/packet/upload`) |
| GET | `/v1/metrics/summary` | p50/p95 e2e & TTFT, degrade rate, $ |

**File upload** — paste text *or* upload `.txt`/`.md` files. In the UI, use the "Upload file" buttons under each release; via the API use the `*/upload` endpoints:

```bash
curl -s -X POST http://127.0.0.1:43125/v1/packet/upload \
  -F "current_file=@data/samples/acme_q2_2026.txt" \
  -F "prior_file=@data/samples/acme_q1_2026.txt" \
  -F "ticker=ACME" -F "mode=thorough"
```

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
- **Swap-ready LLM**: `mock` for CI/demo; `ollama` for local models; `api` for OpenAI-compatible keys.

## Layout

```
backend/app/
  agents/          extractor, diff_normalizer, risk_guidance, questions_writer
  llm/             mock + ollama + api (OpenAI-compatible)
  rag/store.py     ACME/NXLB context seed (SQLite)
  metrics/         SQLite collector + summary
  orchestrator.py  graph + SSE
  main.py          FastAPI
frontend/index.html
data/samples/      ACME + NXLB Q1/Q2 releases
data/metrics.db    created at runtime (gitignored)
data/rag.db        created at runtime (gitignored)
scripts/eval_golden.py
tests/
```
