from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

from tendergraph.qualification.service import (
    QualificationService,
    TenderNotFoundError,
)
from tendergraph.rag.evidence import TenderEvidence


class FakeEvidenceRepository:
    def __init__(self, evidence: TenderEvidence | None) -> None:
        self.evidence = evidence

    def fetch(
        self,
        publication_numbers: list[str],
    ) -> list[TenderEvidence]:
        if self.evidence is None:
            raise RuntimeError("Missing evidence")
        assert publication_numbers == [
            self.evidence.publication_number
        ]
        return [self.evidence]


def make_evidence(
    *,
    description: str | None,
    lot_description: str | None = None,
    deadline: datetime | None = None,
) -> TenderEvidence:
    return TenderEvidence(
        citation_id="T1",
        publication_number="123456-2026",
        publication_date=date(2026, 10, 1),
        title="Data platform services",
        description=description,
        lot_description_text=lot_description,
        buyer_name="Example Buyer",
        buyer_country="BEL",
        cpv_codes=["72000000"],
        procedure_type="open",
        contract_natures=["services"],
        estimated_value=Decimal(500000),
        estimated_value_currency="EUR",
        earliest_deadline=deadline,
        latest_deadline=deadline,
        performance_countries=["BEL"],
        performance_regions=[],
        source_html_url=(
            "https://ted.europa.eu/en/notice/-/detail/123456-2026"
        ),
    )


def test_extracts_explicit_hard_gate_and_documents() -> None:
    evidence = make_evidence(
        description=(
            "The supplier must hold ISO 27001 certification. "
            "The bidder shall provide three reference projects from "
            "similar contracts and an ESPD. The procurement concerns "
            "a managed data platform and related analytics services."
        ),
        deadline=datetime(
            2026,
            10,
            20,
            12,
            tzinfo=UTC,
        ),
    )
    service = QualificationService(  # type: ignore[arg-type]
        FakeEvidenceRepository(evidence)
    )

    result = service.qualify(
        evidence.publication_number,
        now=datetime(
            2026,
            10,
            3,
            12,
            tzinfo=UTC,
        ),
    )

    by_key = {
        item.key: item
        for item in result.requirements
    }
    assert by_key["iso_27001"].evidence_strength == "explicit"
    assert by_key["iso_27001"].hard_gate is True
    assert by_key["similar_experience"].evidence_strength == "explicit"
    assert by_key["espd"].evidence_strength == "explicit"
    assert result.risk_level == "high"
    assert result.review_status == "critical_attention"
    assert any(
        risk.key == "hard_gate_iso_27001"
        for risk in result.risks
    )
    assert any(
        document.key == "espd_document"
        for document in result.document_signals
    )


def test_negated_certification_is_only_mentioned() -> None:
    evidence = make_evidence(
        description=(
            "ISO 9001 is not required for participation. "
            "The buyer nevertheless welcomes mature quality processes. "
            "This notice describes the service scope in sufficient detail "
            "for initial supplier triage."
        ),
        deadline=datetime(
            2026,
            11,
            20,
            12,
            tzinfo=UTC,
        ),
    )
    service = QualificationService(  # type: ignore[arg-type]
        FakeEvidenceRepository(evidence)
    )

    result = service.qualify(
        evidence.publication_number,
        now=datetime(
            2026,
            10,
            3,
            12,
            tzinfo=UTC,
        ),
    )

    iso = next(
        item
        for item in result.requirements
        if item.key == "iso_9001"
    )
    assert iso.evidence_strength == "mentioned"
    assert iso.hard_gate is False
    assert not any(
        risk.key == "hard_gate_iso_9001"
        for risk in result.risks
    )


def test_no_indexed_text_returns_insufficient_evidence() -> None:
    evidence = make_evidence(
        description=None,
        lot_description=None,
        deadline=None,
    )
    service = QualificationService(  # type: ignore[arg-type]
        FakeEvidenceRepository(evidence)
    )

    result = service.qualify(
        evidence.publication_number,
        now=datetime(
            2026,
            10,
            3,
            12,
            tzinfo=UTC,
        ),
    )

    assert result.evidence_coverage == "none"
    assert result.review_status == "insufficient_evidence"
    assert result.risk_level == "medium"
    assert result.requirements == []
    assert any(
        risk.key == "no_indexed_requirement_text"
        for risk in result.risks
    )


def test_closed_deadline_is_critical() -> None:
    evidence = make_evidence(
        description=(
            "The notice contains enough descriptive text for review and "
            "does not state a certification or financial threshold here."
        ),
        deadline=datetime(
            2026,
            10,
            1,
            12,
            tzinfo=UTC,
        ),
    )
    service = QualificationService(  # type: ignore[arg-type]
        FakeEvidenceRepository(evidence)
    )

    result = service.qualify(
        evidence.publication_number,
        now=datetime(
            2026,
            10,
            3,
            12,
            tzinfo=UTC,
        ),
    )

    assert result.risk_level == "high"
    assert result.review_status == "critical_attention"
    assert result.risks[0].key == "deadline_closed"


def test_missing_tender_is_translated_to_domain_error() -> None:
    service = QualificationService(  # type: ignore[arg-type]
        FakeEvidenceRepository(None)
    )

    try:
        service.qualify("missing")
    except TenderNotFoundError:
        pass
    else:
        raise AssertionError("Expected TenderNotFoundError")
