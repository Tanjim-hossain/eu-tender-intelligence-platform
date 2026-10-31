from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID

import pytest

from tendergraph.decision.models import (
    ChecklistReviewItem,
    DecisionReviewUpdate,
    StoredDecisionReview,
)
from tendergraph.decision.service import (
    DecisionDossierService,
    SavedOpportunityNotFoundError,
)
from tendergraph.documents.models import (
    DocumentPackageIntelligence,
    PackageRequirementSignal,
    PackageRisk,
    StoredProcurementDocument,
    TenderDocumentPackage,
)
from tendergraph.matching.models import CompanyProfile
from tendergraph.product.models import (
    OpportunitySnapshot,
    ProductAccount,
    ProductState,
    StoredOpportunityState,
)
from tendergraph.qualification.models import (
    QualificationRisk,
    RequirementSignal,
    TenderQualification,
)

ACCOUNT_ID = UUID("11111111-1111-1111-1111-111111111111")
NOW = datetime(2026, 10, 31, 12, tzinfo=UTC)


def _product_state() -> ProductState:
    return ProductState(
        account=ProductAccount(
            id=ACCOUNT_ID,
            account_type="local",
            email=None,
            display_name=None,
            created_at=NOW,
            updated_at=NOW,
        ),
        profile=CompanyProfile(
            company_name="Example Data Studio",
            services=["Data engineering"],
            technologies=["Python"],
            target_countries=["BEL"],
            preferred_min_value=Decimal(100000),
            preferred_max_value=Decimal(500000),
            preferred_value_currency="EUR",
            min_days_to_deadline=7,
        ),
        opportunities=[
            StoredOpportunityState(
                publication_number="123-2026",
                disposition="saved",
                pipeline_stage="reviewing",
                note="Check security certificate.",
                match_score=88,
                snapshot=OpportunitySnapshot(
                    title="Data platform services",
                    buyer_name="Example Buyer",
                    buyer_country="BEL",
                    estimated_value=Decimal(300000),
                    estimated_value_currency="EUR",
                    earliest_deadline=datetime(
                        2026,
                        11,
                        30,
                        tzinfo=UTC,
                    ),
                    source_html_url="https://ted.europa.eu/example",
                ),
                created_at=NOW,
                updated_at=NOW,
            )
        ],
    )


class FakeProductRepository:
    def __init__(self, state: ProductState | None = None) -> None:
        self.state = state if state is not None else _product_state()

    def get_state(self, account_id: UUID) -> ProductState | None:
        assert account_id == ACCOUNT_ID
        return self.state


class FakeReviewRepository:
    def __init__(self) -> None:
        self.review: StoredDecisionReview | None = None

    def get(
        self,
        account_id: UUID,
        publication_number: str,
    ) -> StoredDecisionReview | None:
        assert account_id == ACCOUNT_ID
        assert publication_number == "123-2026"
        return self.review

    def upsert(
        self,
        account_id: UUID,
        publication_number: str,
        update: DecisionReviewUpdate,
    ) -> StoredDecisionReview:
        self.review = StoredDecisionReview(
            account_id=account_id,
            publication_number=publication_number,
            items=update.items,
            reviewer_note=update.reviewer_note,
            created_at=NOW,
            updated_at=NOW,
        )
        return self.review


class FakeQualificationService:
    def __init__(self) -> None:
        self.deadline = datetime(2026, 11, 30, tzinfo=UTC)

    def qualify(self, publication_number: str) -> TenderQualification:
        assert publication_number == "123-2026"
        return TenderQualification(
            publication_number=publication_number,
            publication_date=date(2026, 10, 1),
            title="Data platform services",
            buyer_name="Example Buyer",
            buyer_country="BEL",
            procedure_type="open",
            estimated_value=Decimal(300000),
            estimated_value_currency="EUR",
            earliest_deadline=self.deadline,
            source_html_url="https://ted.europa.eu/example",
            review_status="critical_attention",
            risk_level="high",
            evidence_coverage="substantive",
            requirements=[
                RequirementSignal(
                    key="iso_27001",
                    category="security",
                    label="ISO 27001 certification",
                    evidence_strength="explicit",
                    evidence="Supplier must hold ISO 27001.",
                    source_section="description",
                    hard_gate=True,
                )
            ],
            document_signals=[],
            risks=[
                QualificationRisk(
                    key="hard_gate_iso_27001",
                    severity="high",
                    message="Explicit potential hard gate detected: ISO 27001 certification.",
                    evidence="Supplier must hold ISO 27001.",
                    source_section="description",
                )
            ],
            next_actions=[],
            disclaimer="verify",
        )


class FakeDocumentService:
    def package(self, publication_number: str) -> TenderDocumentPackage:
        assert publication_number == "123-2026"
        return TenderDocumentPackage(
            publication_number=publication_number,
            title="Data platform services",
            source_xml_url="https://ted.europa.eu/example.xml",
            package_status="ingested",
            documents=[
                StoredProcurementDocument(
                    document_id="spec",
                    source_url="https://buyer.example/spec.pdf",
                    restricted=False,
                    restriction_code=None,
                    official_languages=["ENG"],
                    unofficial_languages=[],
                    status="extracted",
                    final_url="https://buyer.example/spec.pdf",
                    content_type="application/pdf",
                    byte_count=1000,
                    sha256="a" * 64,
                    cache_path="data/documents/spec.pdf",
                    extraction_method="pdftotext",
                    extracted_characters=2200,
                    chunk_count=4,
                    page_count=2,
                    error=None,
                    updated_at=NOW,
                )
            ],
            extracted_document_count=1,
            restricted_document_count=0,
            failed_document_count=0,
            discovered_at=NOW,
            updated_at=NOW,
            error=None,
            disclaimer="verify",
        )

    def intelligence(
        self,
        publication_number: str,
    ) -> DocumentPackageIntelligence:
        assert publication_number == "123-2026"
        return DocumentPackageIntelligence(
            publication_number=publication_number,
            package_status="ingested",
            coverage="substantive",
            documents_considered=1,
            total_extracted_characters=2200,
            requirements=[
                PackageRequirementSignal(
                    key="iso_27001",
                    category="security",
                    label="ISO 27001 certification",
                    evidence_strength="explicit",
                    evidence="The contractor must hold ISO 27001.",
                    document_id="spec",
                    source_url="https://buyer.example/spec.pdf",
                    chunk_id="spec:0002",
                    page_number=12,
                    section_title="Eligibility",
                    hard_gate=True,
                )
            ],
            risks=[
                PackageRisk(
                    key="hard_gate_iso_27001",
                    severity="high",
                    message="Explicit potential hard gate detected in procurement document.",
                    document_id="spec",
                )
            ],
            next_actions=[],
            disclaimer="verify",
        )


def _service(
    *,
    product: FakeProductRepository | None = None,
    reviews: FakeReviewRepository | None = None,
    qualification: FakeQualificationService | None = None,
) -> tuple[DecisionDossierService, FakeReviewRepository, FakeQualificationService]:
    review_repository = reviews or FakeReviewRepository()
    qualification_service = qualification or FakeQualificationService()
    return (
        DecisionDossierService(
            product_repository=(product or FakeProductRepository()),  # type: ignore[arg-type]
            review_repository=review_repository,  # type: ignore[arg-type]
            qualification_service=qualification_service,  # type: ignore[arg-type]
            document_service=FakeDocumentService(),  # type: ignore[arg-type]
            now_provider=lambda: NOW,
        ),
        review_repository,
        qualification_service,
    )


def test_dossier_prefers_exact_document_provenance_and_blocks_unverified_gate() -> None:
    service, _, _ = _service()

    dossier = service.dossier(ACCOUNT_ID, "123-2026")

    assert dossier.strategic_fit == "strong"
    assert dossier.deadline_readiness == "open"
    assert dossier.document_coverage == "substantive"
    assert dossier.review_readiness == "critical_attention"
    assert dossier.evidence_summary.hard_gate_count == 1

    requirement = dossier.checklist[0]
    assert requirement.key == "iso_27001"
    assert requirement.source_kind == "procurement_document"
    assert requirement.page_number == 12
    assert requirement.section_title == "Eligibility"
    assert requirement.chunk_id == "spec:0002"
    assert requirement.manual_status == "unreviewed"


def test_verified_hard_gate_can_move_dossier_to_human_bid_review() -> None:
    service, reviews, _ = _service()

    updated = service.update_review(
        ACCOUNT_ID,
        "123-2026",
        DecisionReviewUpdate(
            items=[
                ChecklistReviewItem(
                    key="iso_27001",
                    status="verified",
                    note="Certificate valid through bid period.",
                )
            ],
            reviewer_note="Security evidence checked.",
        ),
    )

    assert reviews.review is not None
    assert updated.review_readiness == "ready_for_bid_review"
    assert updated.evidence_summary.hard_gates_verified == 1
    assert updated.evidence_summary.verified_count == 1
    assert updated.reviewer_note == "Security evidence checked."
    assert updated.checklist[0].manual_note == "Certificate valid through bid period."


def test_closed_deadline_overrides_other_readiness_signals() -> None:
    qualification = FakeQualificationService()
    qualification.deadline = datetime(2026, 10, 1, tzinfo=UTC)
    service, _, _ = _service(qualification=qualification)

    dossier = service.dossier(ACCOUNT_ID, "123-2026")

    assert dossier.deadline_readiness == "closed"
    assert dossier.review_readiness == "deadline_closed"


def test_unknown_review_key_is_rejected() -> None:
    service, _, _ = _service()

    with pytest.raises(ValueError, match="Unknown dossier checklist key"):
        service.update_review(
            ACCOUNT_ID,
            "123-2026",
            DecisionReviewUpdate(
                items=[
                    ChecklistReviewItem(
                        key="invented_requirement",
                        status="verified",
                    )
                ]
            ),
        )


def test_dossier_requires_saved_opportunity() -> None:
    state = _product_state()
    state.opportunities = []
    service, _, _ = _service(product=FakeProductRepository(state))

    with pytest.raises(SavedOpportunityNotFoundError):
        service.dossier(ACCOUNT_ID, "123-2026")
