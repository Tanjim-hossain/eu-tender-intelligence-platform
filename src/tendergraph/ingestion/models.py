from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class TedNotice(BaseModel):
    """Raw TED notice returned by the Search API."""

    model_config = ConfigDict(
        populate_by_name=True,
        extra="allow",
    )

    notice_type: str = Field(alias="notice-type")
    publication_number: str = Field(alias="publication-number")
    publication_date: str = Field(alias="publication-date")

    classification_cpv: list[str] = Field(
        default_factory=list,
        alias="classification-cpv",
    )

    buyer_name: dict[str, list[str]] = Field(
        default_factory=dict,
        alias="buyer-name",
    )

    buyer_country: list[str] = Field(
        default_factory=list,
        alias="buyer-country",
    )

    notice_title: dict[str, str] = Field(
        default_factory=dict,
        alias="notice-title",
    )

    links: dict[str, dict[str, str]] = Field(
        default_factory=dict,
    )


class TedSearchResponse(BaseModel):
    """Envelope returned by the TED Search API."""

    model_config = ConfigDict(
        populate_by_name=True,
        extra="allow",
    )

    notices: list[TedNotice]

    total_notice_count: int = Field(
        alias="totalNoticeCount",
    )

    iteration_next_token: str | None = Field(
        default=None,
        alias="iterationNextToken",
    )

    timed_out: bool = Field(
        alias="timedOut",
    )


class TedSearchRequest(BaseModel):
    """Validated request parameters for TED Search API."""

    query: str
    fields: list[str]
    page: int = 1
    limit: int = 20
    scope: str = "ALL"
    check_query_syntax: bool = Field(
        default=False,
        alias="checkQuerySyntax",
    )
    pagination_mode: str = Field(
        default="PAGE_NUMBER",
        alias="paginationMode",
    )
    only_latest_versions: bool = Field(
        default=True,
        alias="onlyLatestVersions",
    )

    model_config = ConfigDict(
        populate_by_name=True,
    )

    def to_api_payload(self) -> dict[str, Any]:
        return self.model_dump(
            by_alias=True,
            exclude_none=True,
        )
