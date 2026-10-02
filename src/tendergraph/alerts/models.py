from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class AlertPreferencesUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    min_match_score: float = Field(default=70.0, ge=0, le=100)
    lookback_days: int = Field(default=14, ge=1, le=90)
    max_items: int = Field(default=10, ge=1, le=50)


class AlertPreferences(AlertPreferencesUpdate):
    last_refreshed_at: datetime | None = None


class TenderAlertItem(BaseModel):
    publication_number: str
    publication_date: date
    title: str
    buyer_name: str | None
    buyer_country: str
    estimated_value: Decimal | None
    estimated_value_currency: str | None
    earliest_deadline: datetime | None
    source_html_url: str
    match_score: float = Field(ge=0, le=100)
    why_matches: list[str]
    risks: list[str]
    detected_at: datetime
    seen_at: datetime | None = None

    @property
    def unread(self) -> bool:
        return self.seen_at is None


class AlertDigest(BaseModel):
    account_id: UUID
    profile_name: str
    generated_at: datetime
    last_refreshed_at: datetime | None
    unread_count: int = Field(ge=0)
    total_count: int = Field(ge=0)
    items: list[TenderAlertItem]


class AlertRefreshResult(BaseModel):
    checked_at: datetime
    eligible_count: int = Field(ge=0)
    new_count: int = Field(ge=0)
    digest: AlertDigest


class AlertSeenResponse(BaseModel):
    status: str = "seen"
