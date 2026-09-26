from __future__ import annotations

import httpx

from tendergraph.rag.errors import GenerationUnavailable
from tendergraph.rag.settings import RAGSettings


class OllamaProvider:
    """Generate against the local Ollama daemon, with no automatic retries."""

    def __init__(
        self, settings: RAGSettings, *, client: httpx.Client | None = None
    ) -> None:
        if settings.provider != "ollama":
            raise ValueError("OllamaProvider requires provider='ollama'")
        self._settings = settings
        self._owns_client = client is None
        self._client = (
            client
            if client is not None
            else httpx.Client(
                timeout=settings.timeout_seconds,
                trust_env=False,
                follow_redirects=False,
            )
        )

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def generate(self, *, system_prompt: str, user_prompt: str) -> str:
        try:
            response = self._client.post(
                self._settings.ollama_url.rstrip("/") + "/api/generate",
                json={
                    "model": self._settings.model,
                    "system": system_prompt,
                    "prompt": user_prompt,
                    "stream": False,
                    "options": {
                        "temperature": 0,
                        "num_predict": self._settings.max_output_tokens,
                    },
                },
                timeout=self._settings.timeout_seconds,
            )
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise GenerationUnavailable(
                "Local Ollama unavailable; check the daemon and installed model"
            ) from exc

        if not isinstance(payload, dict):
            raise GenerationUnavailable("Ollama returned an invalid response")
        text = payload.get("response")
        if (
            payload.get("error")
            or payload.get("done") is not True
            or payload.get("done_reason") == "length"
            or not isinstance(text, str)
            or not text.strip()
        ):
            raise GenerationUnavailable("Ollama returned empty or incomplete output")
        return text.strip()
