"""LLM provider interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
import os


@dataclass
class LLMResult:
    text: str
    input_tokens: int
    output_tokens: int
    model: str


class LLMProvider(ABC):
    @abstractmethod
    async def complete(self, prompt: str, *, system: str | None = None, fast: bool = False) -> LLMResult:
        raise NotImplementedError


def get_llm_provider() -> LLMProvider:
    name = os.getenv("LLM_PROVIDER", "mock").lower().strip()
    if name == "ollama":
        from backend.app.llm.ollama import OllamaProvider

        return OllamaProvider()
    if name == "api":
        from backend.app.llm.api import ApiProvider

        return ApiProvider()
    from backend.app.llm.mock import MockProvider

    return MockProvider()
