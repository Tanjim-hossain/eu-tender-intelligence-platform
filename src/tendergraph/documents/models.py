from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

DocumentStatus = Literal[
    "discovered",
    "restricted",
    "extracted",
    "fetched",
    "unsupported",
    "access_denied",
    "failed",
]
PackageStatus = Literal[
    "not_ingested",
    "ingested",
    "partial",
    "restricted_only",
    "failed",
]
PackageCoverage = Literal["none", "partial", "substantive"]
EvidenceStrength = Literal["explicit", "mentioned"]


class ProcurementDocumentReference(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_id: str = Field(min_length=1, max_length=300)
    source_url: str = Field(min_length=1, max_length=4000)
    restricted: bool = False
    restriction_code: str | None = Field(default=None, max_length=100)
    official_languages: list[str] = Field(default_factory=list, max_length=30)
    unofficial_languages: list[str] = Field(default_factory=list, max_length=30)


class StoredProcurementDocument(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_id: str
    source_url: str
    restricted: bool
    restriction_code: str | None
    official_languages: list[str]
    unofficial_languages: list[str]
    status: DocumentStatus
    final_url: str | None = None
    content_type: str | None = None
    byte_count: int | None = Field(default=None, ge=0)
    sha256: str | None = None
    cache_path: str | None = None
    extraction_method: str | None = None
    extracted_characters: int = Field(default=0, ge=0)
    error: str | None = None
    updated_at: datetime | None = None


class TenderDocumentPackage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    publication_number: str
    title: str | None
    source_xml_url: str | None
    package_status: PackageStatus
    documents: list[StoredProcurementDocument]
    extracted_document_count: int = Field(ge=0)
    restricted_document_count: int = Field(ge=0)
    failed_document_count: int = Field(ge=0)
    discovered_at: datetime | None = None
    updated_at: datetime | None = None
    error: str | None = None
    disclaimer: str


class DocumentIngestRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fetch_documents: bool = True
    force: bool = False


class PackageRequirementSignal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str
    category: str
    label: str
    evidence_strength: EvidenceStrength
    evidence: str
    document_id: str
    source_url: str
    hard_gate: bool = False


class PackageRisk(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str
    severity: Literal["low", "medium", "high", "unknown"]
    message: str
    document_id: str | None = None


class DocumentPackageIntelligence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    publication_number: str
    package_status: PackageStatus
    coverage: PackageCoverage
    documents_considered: int = Field(ge=0)
    total_extracted_characters: int = Field(ge=0)
    requirements: list[PackageRequirementSignal]
    risks: list[PackageRisk]
    next_actions: list[str] = Field(max_length=8)
    disclaimer: str
