from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from tendergraph.product.models import ProductAccount


class AuthRegisterRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=12, max_length=200)
    display_name: str | None = Field(default=None, max_length=200)
    local_account_id: UUID | None = None

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        normalized = value.strip().lower()
        if (
            normalized.count("@") != 1
            or any(character.isspace() for character in normalized)
        ):
            raise ValueError("email must be a valid address")
        local, domain = normalized.rsplit("@", 1)
        if not local or not domain or domain.startswith(".") or domain.endswith("."):
            raise ValueError("email must be a valid address")
        return normalized

    @field_validator("display_name")
    @classmethod
    def normalize_display_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None


class AuthLoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=200)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.strip().lower()


class AuthStatusResponse(BaseModel):
    authenticated: bool
    account: ProductAccount | None = None
    expires_at: datetime | None = None


class AuthLogoutResponse(BaseModel):
    status: str = "signed_out"
