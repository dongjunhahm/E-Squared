"""OpenAI-compatible chat completions provider (LLM_PROVIDER=api)."""

from __future__ import annotations

import os

import httpx

from backend.app.llm.base import LLMProvider, LLMResult


class ApiProvider(LLMProvider):
    """Calls any OpenAI-compatible /v1/chat/completions endpoint."""

    def __init__(self) -> None:
        # Accept either API_KEY (generic OpenAI-compatible) or CURSOR_API_KEY.
        self.api_key = (os.getenv("API_KEY") or os.getenv("CURSOR_API_KEY") or "").strip()
        self.base_url = os.getenv("API_BASE_URL", "https://api.openai.com/v1").rstrip("/")
        self.model = os.getenv("API_MODEL", "gpt-4o-mini")
        self.model_fast = os.getenv("API_MODEL_FAST", "gpt-4o-mini")
        if not self.api_key:
            raise RuntimeError(
                "LLM_PROVIDER=api requires API_KEY or CURSOR_API_KEY in .env "
                "(paste your key, and point API_BASE_URL at a matching OpenAI-compatible endpoint)."
            )

    async def complete(self, prompt: str, *, system: str | None = None, fast: bool = False) -> LLMResult:
        model = self.model_fast if fast else self.model
        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        async with httpx.AsyncClient(timeout=90.0) as client:
            resp = await client.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json={"model": model, "messages": messages, "temperature": 0.2},
            )
            resp.raise_for_status()
            data = resp.json()
        choices = data.get("choices") or []
        text = ""
        if choices:
            text = (choices[0].get("message") or {}).get("content") or ""
        usage = data.get("usage") or {}
        input_tokens = int(usage.get("prompt_tokens") or max(1, len(prompt) // 4))
        output_tokens = int(usage.get("completion_tokens") or max(1, len(text) // 4))
        return LLMResult(text=text, input_tokens=input_tokens, output_tokens=output_tokens, model=model)
