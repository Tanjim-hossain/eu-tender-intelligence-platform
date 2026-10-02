from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from tendergraph.matching.models import CompanyProfile

AccountType = Literal["local", "registered"]
OpportunityDisposition = Literal["saved", "ignored"]
PipelineStage = Literal["reviewing", "qualified", "bid_planned", "no_bid"]


class ProductAccount(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    account_type: AccountType
    email: str | None
    display_name: str | None
    created_at: datetime
    updated_at: datetime


class OpportunitySnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=2000)
    buyer_name: str | None = Field(default=None, max_length=1000)
    buyer_country: str = Field(min_length=1, max_length=16)
    estimated_value: Decimal | None = Field(default=None, ge=0)
    estimated_value_currency: str | None = Field(default=None, min_length=3, max_length=3)
    earliest_deadline: datetime | None = None
    source_html_url: str = Field(min_length=1, max_length=4000)


class OpportunityStateUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    disposition: OpportunityDisposition
    pipeline_stage: PipelineStage | None = None
    note: str = Field(default="", max_length=5000)
    match_score: float | None = Field(default=None, ge=0, le=100)
    snapshot: OpportunitySnapshot | None = None

    @model_validator(mode="after")
    def validate_disposition(self) -> Self:
        if self.disposition == "saved" and self.snapshot is None:
            raise ValueError("saved opportunities require a snapshot")
        if self.disposition == "ignored" and self.pipeline_stage is not None:
            raise ValueError("ignored opportunities cannot have a pipeline stage")
        return self


class StoredOpportunityState(BaseModel):
    publication_number: str
    disposition: OpportunityDisposition
    pipeline_stage: PipelineStage | None
    note: str
    match_score: float | None
    snapshot: OpportunitySnapshot | None
    created_at: datetime
    updated_at: datetime


class ProductState(BaseModel):
    account: ProductAccount
    profile: CompanyProfile | None
    opportunities: list[StoredOpportunityState]
