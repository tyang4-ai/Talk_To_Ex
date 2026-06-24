"""Thin httpx client for the local Ollama server (chat + embeddings).

Bound to ``settings.ollama_base_url`` (localhost only — never tunnelled). The
underlying httpx client is injectable so tests can pass a fake transport without
a running Ollama. Params are always explicit per spec §9: ``num_ctx`` defaults
to 8192 (Ollama's silent default of 4K is too small) and ``keep_alive='-1'``
keeps the model resident between turns.
"""
from __future__ import annotations

from typing import Optional

import httpx

from ..config import settings


class OllamaClient:
    """Calls the Ollama HTTP API. Inject ``http`` (an ``httpx.Client``) in tests."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        embed_model: Optional[str] = None,
        http: Optional[httpx.Client] = None,
        timeout: float = 120.0,
    ) -> None:
        self.base_url = (base_url or settings.ollama_base_url).rstrip("/")
        self.model = model or settings.ollama_model
        self.embed_model = embed_model or settings.ollama_embed_model
        self._http = http
        self._timeout = timeout

    def _post(self, path: str, payload: dict) -> dict:
        """POST JSON to the Ollama API. Reuse an injected client; otherwise build
        a transient client and close it (so the live path never leaks FDs)."""
        if self._http is not None:
            resp = self._http.post(f"{self.base_url}{path}", json=payload)
            resp.raise_for_status()
            return resp.json()
        with httpx.Client(base_url=self.base_url, timeout=self._timeout) as client:
            resp = client.post(f"{self.base_url}{path}", json=payload)
            resp.raise_for_status()
            return resp.json()

    def chat(
        self,
        messages: list[dict],
        *,
        num_ctx: int = 8192,
        temperature: float = 0.8,
    ) -> str:
        """POST /api/chat with ``stream:false``; return the assistant content."""
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "keep_alive": "-1",
            "options": {"num_ctx": num_ctx, "temperature": temperature},
        }
        data = self._post("/api/chat", payload)
        return data["message"]["content"]

    def embed(self, text: str) -> list[float]:
        """POST /api/embeddings; return the embedding vector (optional RAG)."""
        payload = {"model": self.embed_model, "prompt": text, "keep_alive": "-1"}
        data = self._post("/api/embeddings", payload)
        return data["embedding"]
