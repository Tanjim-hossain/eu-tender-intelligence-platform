from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def _clean_term_list(values: list[str]) -> list[str]:
    cleaned: list[str] = []
    seen: set[str] = set()
    for value in values:
        term = " ".join(value.split())
        key = term.casefold()
        if term and key not in seen:
            cleaned.append(term)
            seen.add(key)
    return cleaned


class CompanyProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    company_name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    services: list[str] = Field(min_length=1, max_length=30)
    technologies: list[str] = Field(default_factory=list, max_length=30)
    industries: list[str] = Field(default_factory=list, max_length=20)
    keywords: list[str] = Field(default_factory=list, max_length=30)
    target_countries: list[str] = Field(default_factory=list, max_length=30)
    preferred_min_value: Decimal | None = Field(default=None, ge=0)
    preferred_max_value: Decimal | None = Field(default=None, ge=0)
    preferred_value_currency: str = Field(default="EUR", min_length=3, max_length=3)
    min_days_to_deadline: int = Field(default=7, ge=0, le=180)

    @field_validator("company_name")
    @classmethod
    def clean_company_name(cls, value: str) -> str:
        cleaned = " ".join(value.split())
        if not cleaned:
            raise ValueError("company_name must not be blank")
        return cleaned

    @field_validator("description")
    @classmethod
    def clean_description(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = " ".join(value.split())
        return cleaned or None

    @field_validator("services")
    @classmethod
    def clean_services(cls, values: list[str]) -> list[str]:
        cleaned = _clean_term_list(values)
        if not cleaned:
            raise ValueError("services must include at least one non-blank term")
        return cleaned

    @field_validator("technologies", "industries", "keywords")
    @classmethod
    def clean_optional_terms(cls, values: list[str]) -> list[str]:
        return _clean_term_list(values)

    @field_validator("target_countries")
    @classmethod
    def clean_countries(cls, values: list[str]) -> list[str]:
        cleaned: list[str] = []
        seen: set[str] = set()
        for value in values:
            country = value.strip().upper()
            if len(country) != 3:
                raise ValueError(
                    "target_countries must use three-letter country codes"
                )
            if country not in seen:
                cleaned.append(country)
                seen.add(country)
        return cleaned

    @field_validator("preferred_value_currency")
    @classmethod
    def clean_currency(cls, value: str) -> str:
        cleaned = value.strip().upper()
        if len(cleaned) != 3:
            raise ValueError(
                "preferred_value_currency must use a three-letter code"
            )
        return cleaned

    @model_validator(mode="after")
    def validate_value_range(self) -> Self:
        if (
            self.preferred_min_value is not None
            and self.preferred_max_value is not None
            and self.preferred_min_value > self.preferred_max_value
        ):
            raise ValueError(
                "preferred_min_value must not exceed preferred_max_value"
            )
        return self


ValueStatus = Literal[
    "not_configured",
    "within_range",
    "below_range",
    "above_range",
    "unknown",
    "currency_mismatch",
]
DeadlineStatus = Literal["open", "soon", "closed", "unknown"]
CountryStatus = Literal["not_configured", "matched", "mismatched"]


class MatchSignals(BaseModel):
    semantic_fit: float = Field(ge=0, le=1)
    country_fit: float = Field(ge=0, le=1)
    value_fit: float = Field(ge=0, le=1)
    deadline_fit: float = Field(ge=0, le=1)
    country_status: CountryStatus
    value_status: ValueStatus
    deadline_status: DeadlineStatus
    days_to_deadline: int | None


class TenderMatch(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    publication_number: str
    publication_date: date
    title: str
    buyer_name: str | None
    buyer_country: str
    procedure_type: str | None
    estimated_value: Decimal | None
    estimated_value_currency: str | None
    earliest_deadline: datetime | None
    source_html_url: str

    match_score: float = Field(ge=0, le=100)
    signals: MatchSignals
    why_matches: list[str]
    risks: list[str]

    rrf_score: float
    lexical_rank: int | None
    semantic_rank: int | None
    semantic_score: float | None


class CompanyMatchResult(BaseModel):
    profile_name: str
    query: str
    count: int
    matches: list[TenderMatch]
