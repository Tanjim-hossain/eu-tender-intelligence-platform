from __future__ import annotations

import os
from dataclasses import dataclass

from openai import APIError, OpenAI

from tendergraph.rag.errors import GenerationUnavailable

DEFAULT_OPENAI_MODEL = "gpt-5.6-luna"
DEFAULT_MAX_OUTPUT_TOKENS = 800


@dataclass(frozen=True, slots=True)
class OpenAIProviderConfig:
    model: str = DEFAULT_OPENAI_MODEL
    max_output_tokens: int = DEFAULT_MAX_OUTPUT_TOKENS
    timeout_seconds: float = 120.0

    def __post_init__(self) -> None:
        if not self.model.strip():
            raise ValueError("OpenAI model must not be empty")

        if self.max_output_tokens <= 0:
            raise ValueError("max_output_tokens must be positive")

        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")


class OpenAIProvider:
    def __init__(
        self,
        config: OpenAIProviderConfig | None = None,
        *,
        client: OpenAI | None = None,
        api_key: str | None = None,
    ) -> None:
        self.config = config if config is not None else OpenAIProviderConfig()

        self._owns_client = client is None
        if client is not None:
            self._client = client
            return

        api_key = api_key or os.getenv("OPENAI_API_KEY")

        if not api_key:
            raise RuntimeError("OPENAI_API_KEY is not configured")

        self._client = OpenAI(
            api_key=api_key,
            timeout=self.config.timeout_seconds,
            max_retries=0,
        )

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def generate(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
    ) -> str:
        try:
            response = self._client.responses.create(
                model=self.config.model,
                instructions=system_prompt,
                input=user_prompt,
                max_output_tokens=(self.config.max_output_tokens),
            )
        except APIError as exc:
            raise GenerationUnavailable(
                "Configured OpenAI provider unavailable"
            ) from exc

        if getattr(response, "status", "completed") != "completed":
            raise GenerationUnavailable("OpenAI returned incomplete output")

        text = response.output_text.strip()

        if not text:
            raise GenerationUnavailable("OpenAI returned an empty response")

        return text
