from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

RequirementCategory = Literal[
    "certification",
    "security",
    "financial",
    "experience",
    "staffing",
    "legal",
    "technical",
]
EvidenceStrength = Literal["explicit", "mentioned"]
EvidenceSection = Literal[
    "description",
    "lot_description",
    "deadline",
]
RiskSeverity = Literal["low", "medium", "high", "unknown"]
ReviewStatus = Annotated[
    str,
    Field(
        pattern=(
            "^(no_flags|attention|critical_attention|"
            "insufficient_evidence)$"
        )
    ),
]
EvidenceCoverage = Literal["none", "limited", "substantive"]


class RequirementSignal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str
    category: RequirementCategory
    label: str
    evidence_strength: EvidenceStrength
    evidence: str
    source_section: EvidenceSection
    hard_gate: bool = False


class DocumentSignal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str
    label: str
    evidence: str
    source_section: EvidenceSection


class QualificationRisk(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str
    severity: RiskSeverity
    message: str
    evidence: str | None = None
    source_section: EvidenceSection | None = None


class TenderQualification(BaseModel):
    model_config = ConfigDict(extra="forbid")

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

    review_status: ReviewStatus
    risk_level: RiskSeverity
    evidence_coverage: EvidenceCoverage
    requirements: list[RequirementSignal]
    document_signals: list[DocumentSignal]
    risks: list[QualificationRisk]
    next_actions: list[str] = Field(max_length=8)
    disclaimer: str
