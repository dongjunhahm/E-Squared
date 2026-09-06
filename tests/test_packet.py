"""Smoke tests for AnalystPacket schema and /v1/packet."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.schemas import AnalystPacket, JobRequest, Mode


ROOT = Path(__file__).resolve().parents[1]
SAMPLES = ROOT / "data" / "samples"


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    monkeypatch.setenv("METRICS_DB_PATH", str(tmp_path / "metrics.db"))
    monkeypatch.setenv("RAG_DB_PATH", str(tmp_path / "rag.db"))
    # Reset singletons so env paths apply
    import backend.app.metrics.collector as mc
    import backend.app.rag.store as rs

    mc._collector = None
    rs._store = None
    return TestClient(app)


def test_job_request_schema():
    req = JobRequest(current_text="hello", prior_text="prior", mode=Mode.fast)
    assert req.mode == Mode.fast
    assert req.current_text == "hello"


def test_packet_endpoint_acme(client):
    current = (SAMPLES / "acme_q2_2026.txt").read_text()
    prior = (SAMPLES / "acme_q1_2026.txt").read_text()
    resp = client.post(
        "/v1/packet",
        json={"current_text": current, "prior_text": prior, "ticker": "ACME", "mode": "thorough"},
    )
    assert resp.status_code == 200
    packet = AnalystPacket.model_validate(resp.json())
    assert packet.ticker == "ACME"
    assert packet.trace_id
    assert "extractor" in packet.agents_run
    assert "diff_normalizer" in packet.agents_run
    assert len(packet.diffs) >= 3
    labels = {d.label for d in packet.diffs}
    assert "Revenue" in labels
    assert "GAAP EPS" in labels
    # GAAP EPS declined → critical expected
    gaap = next(d for d in packet.diffs if d.label == "GAAP EPS")
    assert gaap.severity.value == "critical"
    assert packet.summary
    assert len(packet.questions) >= 1
    # Citations present on at least one diff
    assert any(d.citations for d in packet.diffs)


def test_health_and_metrics(client):
    h = client.get("/health")
    assert h.status_code == 200
    assert h.json()["status"] == "ok"
    assert h.json()["llm_provider"] == "mock"

    # seed one run
    current = (SAMPLES / "nxlb_q2_2026.txt").read_text()
    prior = (SAMPLES / "nxlb_q1_2026.txt").read_text()
    client.post(
        "/v1/packet",
        json={"current_text": current, "prior_text": prior, "mode": "fast"},
    )
    m = client.get("/v1/metrics/summary")
    assert m.status_code == 200
    body = m.json()
    assert body["run_count"] >= 1
    assert body["p50_e2e_ms"] is not None


def test_fast_mode_shallow_questions(client):
    current = (SAMPLES / "acme_q2_2026.txt").read_text()
    prior = (SAMPLES / "acme_q1_2026.txt").read_text()
    thorough = client.post(
        "/v1/packet",
        json={"current_text": current, "prior_text": prior, "mode": "thorough"},
    ).json()
    fast = client.post(
        "/v1/packet",
        json={"current_text": current, "prior_text": prior, "mode": "fast"},
    ).json()
    assert len(fast["questions"]) <= len(thorough["questions"])
