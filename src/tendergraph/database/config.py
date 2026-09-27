from __future__ import annotations

from urllib.parse import quote

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class DatabaseSettings(BaseSettings):
    """Local PostgreSQL connection settings."""

    postgres_db: str = "tendergraph"
    postgres_user: str = "tendergraph"
    postgres_password: str = Field(
        default="",
        repr=False,
    )
    postgres_host: str = "localhost"
    postgres_port: int = 5433

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @model_validator(mode="after")
    def validate_password(self) -> DatabaseSettings:
        if not self.postgres_password:
            raise ValueError(
                "POSTGRES_PASSWORD must be set"
            )

        return self

    @property
    def connection_uri(self) -> str:
        return (
            "postgresql://"
            f"{quote(self.postgres_user, safe='')}:"
            f"{quote(self.postgres_password, safe='')}@"
            f"{self.postgres_host}:"
            f"{self.postgres_port}/"
            f"{quote(self.postgres_db, safe='')}"
        )
