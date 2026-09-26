from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)


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
