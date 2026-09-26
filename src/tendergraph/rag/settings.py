from __future__ import annotations

from typing import Literal, Self
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

AnswerMode = Literal["evidence", "ollama", "openai"]


class RAGSettings(BaseSettings):
    """Server-owned settings; a request cannot switch on a paid provider."""

    model_config = SettingsConfigDict(
        env_file=".env", env_prefix="RAG_", extra="ignore"
    )

    provider: AnswerMode = "evidence"
    model: str = ""
    ollama_url: str = "http://127.0.0.1:11434"
    timeout_seconds: float = Field(default=120, gt=0, le=600)
    max_output_tokens: int = Field(default=800, ge=1, le=4096)
    max_context_chars: int = Field(default=40000, ge=2000, le=100000)
    rerank: bool = False
    openai_api_key: SecretStr | None = Field(
        default=None, validation_alias="OPENAI_API_KEY", repr=False
    )

    @model_validator(mode="after")
    def validate_provider(self) -> Self:
        self.model = self.model.strip()
        if self.provider != "evidence" and not self.model:
            raise ValueError("Set RAG_MODEL explicitly for the selected provider")
        if self.provider == "ollama":
            url = urlsplit(self.ollama_url)
            if (
                url.scheme != "http"
                or url.hostname not in {"localhost", "127.0.0.1", "::1"}
                or url.username is not None
                or url.password is not None
                or url.path not in {"", "/"}
                or url.query
                or url.fragment
            ):
                raise ValueError("RAG_OLLAMA_URL must be a local HTTP origin")
            if self.model.endswith(":cloud") or self.model.endswith("-cloud"):
                raise ValueError("Use a locally installed model, not a cloud model")
        return self
