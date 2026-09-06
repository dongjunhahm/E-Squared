"""Optional Ollama adapter (used when LLM_PROVIDER=ollama)."""

from __future__ import annotations

import os

import httpx

from backend.app.llm.base import LLMProvider, LLMResult


class OllamaProvider(LLMProvider):
    def __init__(self) -> None:
        self.base_url = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")
        self.model = os.getenv("OLLAMA_MODEL", "llama3.2")
        self.model_fast = os.getenv("OLLAMA_MODEL_FAST", "llama3.2:1b")

    async def complete(self, prompt: str, *, system: str | None = None, fast: bool = False) -> LLMResult:
        model = self.model_fast if fast else self.model
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                f"{self.base_url}/api/chat",
                json={"model": model, "messages": messages, "stream": False},
            )
            resp.raise_for_status()
            data = resp.json()
        text = data.get("message", {}).get("content", "")
        # Ollama may omit token counts; estimate.
        approx_in = max(1, len(prompt) // 4)
        approx_out = max(1, len(text) // 4)
        return LLMResult(text=text, input_tokens=approx_in, output_tokens=approx_out, model=model)
