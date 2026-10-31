from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

EvidenceReviewStatus = Literal[
    "unreviewed",
    "verified",
    "needs_evidence",
    "not_applicable",
]
DecisionReadiness = Literal[
    "ready_for_bid_review",
    "hold_for_evidence",
    "critical_attention",
    "deadline_closed",
    "user_no_bid",
]
StrategicFitStatus = Literal["strong", "moderate", "weak", "unknown"]
DeadlineReadiness = Literal["open", "urgent", "closed", "unknown"]
DossierSourceKind = Literal["notice", "procurement_document"]
DossierRiskSeverity = Literal["low", "medium", "high", "unknown"]


class ChecklistReviewItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str = Field(min_length=1, max_length=200)
    status: EvidenceReviewStatus = "unreviewed"
    note: str = Field(default="", max_length=1000)


class DecisionReviewUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[ChecklistReviewItem] = Field(default_factory=list, max_length=100)
    reviewer_note: str = Field(default="", max_length=5000)

    @model_validator(mode="after")
    def unique_keys(self) -> DecisionReviewUpdate:
        keys = [item.key for item in self.items]
        if len(keys) != len(set(keys)):
            raise ValueError("decision review item keys must be unique")
        return self


class StoredDecisionReview(BaseModel):
    account_id: UUID
    publication_number: str
    items: list[ChecklistReviewItem]
    reviewer_note: str
    created_at: datetime
    updated_at: datetime


class DossierChecklistItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str
    category: str
    label: str
    source_kind: DossierSourceKind
    evidence_strength: Literal["explicit", "mentioned"]
    hard_gate: bool = False
    evidence: str
    source_url: str | None = None
    document_id: str | None = None
    chunk_id: str | None = None
    page_number: int | None = Field(default=None, ge=1)
    section_title: str | None = None
    manual_status: EvidenceReviewStatus = "unreviewed"
    manual_note: str = ""


class DossierRisk(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str
    severity: DossierRiskSeverity
    message: str
    source_kind: Literal[
        "strategic_fit",
        "deadline",
        "notice",
        "procurement_document",
        "document_coverage",
    ]


class DossierEvidenceSummary(BaseModel):
    requirement_count: int = Field(ge=0)
    hard_gate_count: int = Field(ge=0)
    hard_gates_verified: int = Field(ge=0)
    verified_count: int = Field(ge=0)
    needs_evidence_count: int = Field(ge=0)
    unreviewed_count: int = Field(ge=0)


class BidNoBidDossier(BaseModel):
    model_config = ConfigDict(extra="forbid")

    account_id: UUID
    publication_number: str
    title: str
    buyer_name: str | None
    buyer_country: str
    source_html_url: str
    pipeline_stage: Literal["reviewing", "qualified", "bid", "no_bid"]
    pipeline_note: str
    match_score: float | None = Field(default=None, ge=0, le=100)

    strategic_fit: StrategicFitStatus
    strategic_fit_reasons: list[str]
    deadline_readiness: DeadlineReadiness
    days_to_deadline: int | None

    notice_review_status: str
    notice_risk_level: DossierRiskSeverity
    document_package_status: str
    document_coverage: str

    checklist: list[DossierChecklistItem]
    risks: list[DossierRisk]
    evidence_summary: DossierEvidenceSummary

    review_readiness: DecisionReadiness
    review_message: str
    reviewer_note: str
    next_actions: list[str] = Field(max_length=10)
    disclaimer: str
