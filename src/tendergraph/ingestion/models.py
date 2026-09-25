from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class TedNotice(BaseModel):
    """Raw TED notice returned by the Search API."""

    model_config = ConfigDict(
        populate_by_name=True,
        extra="allow",
    )

    notice_type: str = Field(
        alias="notice-type",
    )

    publication_number: str = Field(
        alias="publication-number",
    )

    publication_date: str = Field(
        alias="publication-date",
    )

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

    description_proc: dict[str, str] = Field(
        default_factory=dict,
        alias="description-proc",
    )

    description_lot: dict[str, list[str]] = Field(
        default_factory=dict,
        alias="description-lot",
    )

    procedure_type: str | None = Field(
        default=None,
        alias="procedure-type",
    )

    contract_nature: list[str] = Field(
        default_factory=list,
        alias="contract-nature",
    )

    deadline: list[str] = Field(
        default_factory=list,
        alias="deadline",
    )

    estimated_value_proc: str | None = Field(
        default=None,
        alias="estimated-value-proc",
    )

    estimated_value_cur_proc: str | None = Field(
        default=None,
        alias="estimated-value-cur-proc",
    )

    place_of_performance_country_proc: list[str] = Field(
        default_factory=list,
        alias="place-of-performance-country-proc",
    )

    place_of_performance_subdiv_proc: list[str] = Field(
        default_factory=list,
        alias="place-of-performance-subdiv-proc",
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

    page: int = Field(
        default=1,
        ge=1,
    )

    limit: int = Field(
        default=20,
        ge=1,
        le=250,
    )

    scope: str = "ALL"

    check_query_syntax: bool = Field(
        default=False,
        alias="checkQuerySyntax",
    )

    pagination_mode: Literal[
        "PAGE_NUMBER",
        "ITERATION",
    ] = Field(
        default="PAGE_NUMBER",
        alias="paginationMode",
    )

    iteration_next_token: str | None = Field(
        default=None,
        alias="iterationNextToken",
    )

    only_latest_versions: bool = Field(
        default=True,
        alias="onlyLatestVersions",
    )

    model_config = ConfigDict(
        populate_by_name=True,
    )

    def to_api_payload(self) -> dict[str, Any]:
        payload = self.model_dump(
            by_alias=True,
            exclude_none=True,
        )

        if self.pagination_mode == "ITERATION":
            payload.pop("page", None)

        return payload
