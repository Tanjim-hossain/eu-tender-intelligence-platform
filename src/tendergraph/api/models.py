from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from tendergraph.rag.settings import AnswerMode


class SearchRequest(BaseModel):
    query: str = Field(
        min_length=1,
        max_length=500,
    )
    limit: int = Field(
        default=10,
        ge=1,
        le=100,
    )
    retrieval_depth: int = Field(
        default=20,
        ge=1,
        le=100,
    )

    @field_validator("query")
    @classmethod
    def normalize_query(
        cls,
        value: str,
    ) -> str:
        cleaned = " ".join(
            value.strip().split()
        )

        if not cleaned:
            raise ValueError(
                "Search query must not be empty"
            )

        return cleaned

    @model_validator(mode="after")
    def validate_retrieval_depth(
        self,
    ) -> Self:
        if self.retrieval_depth < self.limit:
            raise ValueError(
                "retrieval_depth must be "
                "greater than or equal to limit"
            )

        return self


class SearchResult(BaseModel):
    model_config = ConfigDict(
        from_attributes=True
    )

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

    rrf_score: float
    lexical_rank: int | None
    semantic_rank: int | None
    semantic_score: float | None


class SearchResponse(BaseModel):
    query: str
    count: int
    results: list[SearchResult]


class HealthResponse(BaseModel):
    status: str
    database: str
    model: str


class OperationsStatusResponse(BaseModel):
    model_config = ConfigDict(
        from_attributes=True
    )

    overall_status: Literal[
        "ok",
        "refreshing",
        "degraded",
        "stale",
        "unknown",
    ]

    latest_refresh_id: str | None
    latest_refresh_status: Literal[
        "running",
        "completed",
        "failed",
    ] | None
    latest_started_at_utc: datetime | None
    latest_finished_at_utc: datetime | None
    latest_window_end: date | None
    latest_dbt_success: bool | None

    last_successful_refresh_id: str | None
    last_successful_finished_at_utc: (
        datetime | None
    )
    last_successful_window_end: date | None

    expected_data_through: date
    lag_days: int | None
    stale: bool

    last_success_database_rows: int | None
    last_success_embedding_rows: int | None

    failure_stage: str | None
    failure_type: str | None


class AskRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=1, max_length=2000)
    query: str | None = Field(default=None, min_length=1, max_length=500)
    evidence_limit: int = Field(default=5, ge=1, le=10)
    retrieval_depth: int = Field(default=20, ge=1, le=100)

    @field_validator("question", "query")
    @classmethod
    def clean_text(cls, value: str | None) -> str | None:
        if value is None:
            return value
        cleaned = " ".join(value.split())
        if not cleaned:
            raise ValueError("Question and query must not be blank")
        return cleaned

    @model_validator(mode="after")
    def check_depth(self) -> Self:
        if self.retrieval_depth < self.evidence_limit:
            raise ValueError("retrieval_depth must cover evidence_limit")
        return self


class AnswerSource(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    citation_id: str
    publication_number: str
    publication_date: date
    title: str
    buyer_name: str | None
    buyer_country: str
    estimated_value: Decimal | None
    estimated_value_currency: str | None
    earliest_deadline: datetime | None
    source_html_url: str


class AskResponse(BaseModel):
    question: str
    mode: AnswerMode
    status: Literal["evidence_only", "answered", "no_results", "insufficient_evidence"]
    answer: str
    citations: list[str]
    sources: list[AnswerSource]
    context_truncated: bool
