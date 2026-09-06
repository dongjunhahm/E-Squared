"""FastAPI entrypoint — Earnings Diff → Analyst Packet (AgentOps Lite)."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sse_starlette.sse import EventSourceResponse

from backend.app.llm.base import get_llm_provider
from backend.app.metrics.collector import get_metrics_collector
from backend.app.orchestrator import run_packet, stream_packet
from backend.app.schemas import AnalystPacket, HealthResponse, JobRequest, MetricsSummary

load_dotenv()

ROOT = Path(__file__).resolve().parents[2]
FRONTEND_DIR = ROOT / "frontend"

app = FastAPI(title="Earnings Diff → Analyst Packet", version="0.1.0")


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    provider = os.getenv("LLM_PROVIDER", "mock")
    # Touch provider construction to ensure import path works
    _ = get_llm_provider()
    return HealthResponse(llm_provider=provider)


@app.post("/v1/packet", response_model=AnalystPacket)
async def create_packet(req: JobRequest) -> AnalystPacket:
    return await run_packet(req)


@app.post("/v1/packet/stream")
async def create_packet_stream(req: JobRequest) -> EventSourceResponse:
    async def gen():
        async for chunk in stream_packet(req):
            # sse-starlette expects dicts or strings; our chunks are already SSE frames.
            # Parse back into event/data for EventSourceResponse, or yield raw.
            # Prefer yielding structured events:
            lines = chunk.strip().split("\n")
            event = "message"
            data = ""
            for line in lines:
                if line.startswith("event: "):
                    event = line[7:]
                elif line.startswith("data: "):
                    data = line[6:]
            yield {"event": event, "data": data}

    return EventSourceResponse(gen())


@app.get("/v1/metrics/summary", response_model=MetricsSummary)
async def metrics_summary() -> MetricsSummary:
    return get_metrics_collector().summary()


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "index.html")


if FRONTEND_DIR.is_dir():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")
