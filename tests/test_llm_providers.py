"""LLM provider factory tests."""

from __future__ import annotations

import pytest

from backend.app.llm.base import get_llm_provider
from backend.app.llm.mock import MockProvider


def test_get_llm_provider_mock(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    assert isinstance(get_llm_provider(), MockProvider)


def test_get_llm_provider_api_requires_key(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "api")
    monkeypatch.setenv("API_KEY", "")
    monkeypatch.delenv("CURSOR_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="API_KEY"):
        get_llm_provider()


def test_get_llm_provider_api_accepts_cursor_key(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "api")
    monkeypatch.delenv("API_KEY", raising=False)
    monkeypatch.setenv("CURSOR_API_KEY", "crsr-test-not-real")
    monkeypatch.setenv("API_BASE_URL", "https://example.com/v1")
    provider = get_llm_provider()
    from backend.app.llm.api import ApiProvider

    assert isinstance(provider, ApiProvider)
    assert provider.api_key == "crsr-test-not-real"


def test_get_llm_provider_api_wires(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "api")
    monkeypatch.setenv("API_KEY", "test-key-not-real")
    monkeypatch.setenv("API_BASE_URL", "https://example.com/v1")
    monkeypatch.setenv("API_MODEL", "demo-model")
    provider = get_llm_provider()
    from backend.app.llm.api import ApiProvider

    assert isinstance(provider, ApiProvider)
    assert provider.model == "demo-model"
    assert provider.base_url == "https://example.com/v1"
