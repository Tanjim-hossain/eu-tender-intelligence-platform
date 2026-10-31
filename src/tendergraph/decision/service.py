from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from tendergraph.decision.models import (
    BidNoBidDossier,
    ChecklistReviewItem,
    DeadlineReadiness,
    DecisionReadiness,
    DecisionReviewUpdate,
    DossierChecklistItem,
    DossierEvidenceSummary,
    DossierRisk,
    StrategicFitStatus,
)
from tendergraph.decision.repository import DecisionReviewRepository
from tendergraph.documents.service import DocumentService
from tendergraph.product.models import ProductState, StoredOpportunityState
from tendergraph.product.repository import ProductRepository
from tendergraph.qualification.service import QualificationService

DOSSIER_DISCLAIMER = (
    "This dossier consolidates deterministic TenderGraph evidence to support "
    "human bid/no-bid review. It does not determine legal eligibility, predict "
    "award probability, or replace the buyer's official notice and procurement "
    "documents. Manual confirmations are user assertions and should be backed "
    "by documentary evidence."
)


class SavedOpportunityNotFoundError(LookupError):
    """Raised when the requested tender is not saved for the account."""


def _normalize_datetime(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _manual_map(
    review_items: list[ChecklistReviewItem],
) -> dict[str, ChecklistReviewItem]:
    return {item.key: item for item in review_items}


def _strategic_fit(
    opportunity: StoredOpportunityState,
    *,
    target_countries: list[str],
    preferred_min_value: Decimal | None,
    preferred_max_value: Decimal | None,
    preferred_currency: str,
) -> tuple[StrategicFitStatus, list[str], list[DossierRisk]]:
    score = opportunity.match_score
    reasons: list[str] = []
    risks: list[DossierRisk] = []

    status: StrategicFitStatus
    if score is None:
        status = "unknown"
        reasons.append("No stored company-fit score is available for this saved tender.")
    elif score >= 75:
        status = "strong"
        reasons.append(f"Stored company-fit score is strong at {score:.0f}%.")
    elif score >= 55:
        status = "moderate"
        reasons.append(f"Stored company-fit score is moderate at {score:.0f}%.")
    else:
        status = "weak"
        reasons.append(f"Stored company-fit score is weak at {score:.0f}%.")
        risks.append(
            DossierRisk(
                key="strategic_fit_weak",
                severity="medium",
                message="Company fit is weak; confirm strategic rationale before committing bid effort.",
                source_kind="strategic_fit",
            )
        )

    snapshot = opportunity.snapshot
    if snapshot is None:
        return status, reasons, risks

    if target_countries:
        if snapshot.buyer_country.upper() in target_countries:
            reasons.append(
                f"Buyer country {snapshot.buyer_country} is in the configured target markets."
            )
        else:
            risks.append(
                DossierRisk(
                    key="strategic_country_mismatch",
                    severity="medium",
                    message=(
                        f"Buyer country {snapshot.buyer_country} is outside the configured "
                        "target markets."
                    ),
                    source_kind="strategic_fit",
                )
            )

    if preferred_min_value is not None or preferred_max_value is not None:
        value = snapshot.estimated_value
        currency = snapshot.estimated_value_currency
        if value is None or currency is None:
            risks.append(
                DossierRisk(
                    key="strategic_value_unknown",
                    severity="unknown",
                    message="Estimated contract value is unavailable for profile-range review.",
                    source_kind="strategic_fit",
                )
            )
        elif currency.upper() != preferred_currency.upper():
            risks.append(
                DossierRisk(
                    key="strategic_currency_mismatch",
                    severity="medium",
                    message=(
                        f"Tender value uses {currency.upper()} while the company profile "
                        f"uses {preferred_currency.upper()}."
                    ),
                    source_kind="strategic_fit",
                )
            )
        elif preferred_min_value is not None and value < preferred_min_value:
            risks.append(
                DossierRisk(
                    key="strategic_value_below_range",
                    severity="medium",
                    message="Estimated contract value is below the preferred range.",
                    source_kind="strategic_fit",
                )
            )
        elif preferred_max_value is not None and value > preferred_max_value:
            risks.append(
                DossierRisk(
                    key="strategic_value_above_range",
                    severity="medium",
                    message="Estimated contract value is above the preferred range.",
                    source_kind="strategic_fit",
                )
            )
        else:
            reasons.append("Estimated contract value is within the configured range.")

    return status, reasons, risks


def _deadline_readiness(
    deadline: datetime | None,
    *,
    minimum_days: int,
    now: datetime,
) -> tuple[DeadlineReadiness, int | None, DossierRisk | None]:
    if deadline is None:
        return (
            "unknown",
            None,
            DossierRisk(
                key="deadline_unknown",
                severity="unknown",
                message="Submission deadline is unavailable; verify the official TED notice.",
                source_kind="deadline",
            ),
        )

    normalized = _normalize_datetime(deadline)
    seconds = (normalized - now).total_seconds()
    days = int(seconds // 86400)
    if seconds <= 0:
        return (
            "closed",
            days,
            DossierRisk(
                key="deadline_closed",
                severity="high",
                message="The indexed submission deadline has passed.",
                source_kind="deadline",
            ),
        )

    threshold = max(3, minimum_days)
    if days < threshold:
        return (
            "urgent",
            days,
            DossierRisk(
                key="deadline_urgent",
                severity="medium",
                message=(
                    f"Only {days} day(s) remain, below the preferred preparation "
                    f"window of {minimum_days} day(s)."
                ),
                source_kind="deadline",
            ),
        )

    return "open", days, None


class DecisionDossierService:
    def __init__(
        self,
        *,
        product_repository: ProductRepository,
        review_repository: DecisionReviewRepository,
        qualification_service: QualificationService,
        document_service: DocumentService,
        now_provider: Callable[[], datetime] | None = None,
    ) -> None:
        self._product_repository = product_repository
        self._review_repository = review_repository
        self._qualification_service = qualification_service
        self._document_service = document_service
        self._now_provider = now_provider or (lambda: datetime.now(UTC))

    def _saved_opportunity(
        self,
        account_id: UUID,
        publication_number: str,
    ) -> tuple[StoredOpportunityState, ProductState]:
        state = self._product_repository.get_state(account_id)
        if state is None:
            raise SavedOpportunityNotFoundError(publication_number)

        opportunity = next(
            (
                item
                for item in state.opportunities
                if item.publication_number == publication_number
                and item.disposition == "saved"
            ),
            None,
        )
        if opportunity is None or opportunity.snapshot is None:
            raise SavedOpportunityNotFoundError(publication_number)
        return opportunity, state

    def dossier(
        self,
        account_id: UUID,
        publication_number: str,
    ) -> BidNoBidDossier:
        opportunity, state_obj = self._saved_opportunity(
            account_id,
            publication_number,
        )
        state = state_obj
        profile = state.profile
        snapshot = opportunity.snapshot
        if snapshot is None:
            raise SavedOpportunityNotFoundError(publication_number)

        qualification = self._qualification_service.qualify(publication_number)
        package = self._document_service.package(publication_number)
        package_intelligence = self._document_service.intelligence(publication_number)
        review = self._review_repository.get(account_id, publication_number)
        review_items = review.items if review is not None else []
        review_map = _manual_map(review_items)

        target_countries = profile.target_countries if profile is not None else []
        preferred_min_value = profile.preferred_min_value if profile is not None else None
        preferred_max_value = profile.preferred_max_value if profile is not None else None
        preferred_currency = (
            profile.preferred_value_currency
            if profile is not None
            else "EUR"
        )
        minimum_days = profile.min_days_to_deadline if profile is not None else 7

        strategic_fit, strategic_reasons, risks = _strategic_fit(
            opportunity,
            target_countries=target_countries,
            preferred_min_value=preferred_min_value,
            preferred_max_value=preferred_max_value,
            preferred_currency=preferred_currency,
        )

        now = _normalize_datetime(self._now_provider())
        deadline_status, days_to_deadline, deadline_risk = _deadline_readiness(
            qualification.earliest_deadline,
            minimum_days=minimum_days,
            now=now,
        )
        if deadline_risk is not None:
            risks.append(deadline_risk)

        checklist_by_key: dict[str, DossierChecklistItem] = {}

        # Procurement-document evidence wins over notice-only evidence for the
        # same stable requirement key because it can carry page/section provenance.
        for package_requirement in package_intelligence.requirements:
            manual = review_map.get(package_requirement.key)
            checklist_by_key[package_requirement.key] = DossierChecklistItem(
                key=package_requirement.key,
                category=package_requirement.category,
                label=package_requirement.label,
                source_kind="procurement_document",
                evidence_strength=package_requirement.evidence_strength,
                hard_gate=package_requirement.hard_gate,
                evidence=package_requirement.evidence,
                source_url=package_requirement.source_url,
                document_id=package_requirement.document_id,
                chunk_id=package_requirement.chunk_id,
                page_number=package_requirement.page_number,
                section_title=package_requirement.section_title,
                manual_status=(
                    manual.status if manual is not None else "unreviewed"
                ),
                manual_note=manual.note if manual is not None else "",
            )

        for notice_requirement in qualification.requirements:
            if notice_requirement.key in checklist_by_key:
                continue
            manual = review_map.get(notice_requirement.key)
            checklist_by_key[notice_requirement.key] = DossierChecklistItem(
                key=notice_requirement.key,
                category=notice_requirement.category,
                label=notice_requirement.label,
                source_kind="notice",
                evidence_strength=notice_requirement.evidence_strength,
                hard_gate=notice_requirement.hard_gate,
                evidence=notice_requirement.evidence,
                source_url=qualification.source_html_url,
                section_title=notice_requirement.source_section.replace("_", " "),
                manual_status=(
                    manual.status if manual is not None else "unreviewed"
                ),
                manual_note=manual.note if manual is not None else "",
            )

        checklist = sorted(
            checklist_by_key.values(),
            key=lambda item: (
                not item.hard_gate,
                item.category,
                item.label.casefold(),
            ),
        )

        for qualification_risk in qualification.risks:
            risks.append(
                DossierRisk(
                    key=f"notice:{qualification_risk.key}",
                    severity=qualification_risk.severity,
                    message=qualification_risk.message,
                    source_kind="notice",
                )
            )
        for package_risk in package_intelligence.risks:
            risks.append(
                DossierRisk(
                    key=f"package:{package_risk.key}",
                    severity=package_risk.severity,
                    message=package_risk.message,
                    source_kind="procurement_document",
                )
            )

        if package.package_status == "not_ingested":
            risks.append(
                DossierRisk(
                    key="document_package_not_ingested",
                    severity="unknown",
                    message=(
                        "The procurement-document package has not been ingested, "
                        "so mandatory criteria may be missing from this dossier."
                    ),
                    source_kind="document_coverage",
                )
            )
        elif package_intelligence.coverage != "substantive":
            risks.append(
                DossierRisk(
                    key="document_coverage_incomplete",
                    severity="medium",
                    message=(
                        f"Procurement-document coverage is {package_intelligence.coverage}; "
                        "review unread, restricted, or unsupported documents manually."
                    ),
                    source_kind="document_coverage",
                )
            )

        hard_gates = [
            checklist_item
            for checklist_item in checklist
            if checklist_item.hard_gate
        ]
        hard_gates_verified = sum(
            checklist_item.manual_status == "verified"
            for checklist_item in hard_gates
        )
        verified_count = sum(
            checklist_item.manual_status == "verified"
            for checklist_item in checklist
        )
        needs_evidence_count = sum(
            checklist_item.manual_status == "needs_evidence"
            for checklist_item in checklist
        )
        unreviewed_count = sum(
            checklist_item.manual_status == "unreviewed"
            for checklist_item in checklist
        )
        summary = DossierEvidenceSummary(
            requirement_count=len(checklist),
            hard_gate_count=len(hard_gates),
            hard_gates_verified=hard_gates_verified,
            verified_count=verified_count,
            needs_evidence_count=needs_evidence_count,
            unreviewed_count=unreviewed_count,
        )

        unresolved_hard_gates = [
            hard_gate
            for hard_gate in hard_gates
            if hard_gate.manual_status != "verified"
        ]
        unresolved_explicit = [
            checklist_item
            for checklist_item in checklist
            if (
                checklist_item.evidence_strength == "explicit"
                and checklist_item.manual_status
                not in {"verified", "not_applicable"}
            )
        ]
        verified_keys = {
            checklist_item.key
            for checklist_item in checklist
            if checklist_item.manual_status == "verified"
        }

        def high_risk_blocks(risk: DossierRisk) -> bool:
            if risk.severity != "high":
                return False
            marker = "hard_gate_"
            if marker in risk.key:
                requirement_key = risk.key.split(marker, 1)[1]
                return requirement_key not in verified_keys
            return True

        readiness: DecisionReadiness
        if opportunity.pipeline_stage == "no_bid":
            readiness = "user_no_bid"
            message = (
                "This opportunity is already marked No-bid by the user. "
                "The dossier remains available as decision evidence."
            )
        elif deadline_status == "closed":
            readiness = "deadline_closed"
            message = (
                "The indexed deadline has passed. Verify TED before any further bid work."
            )
        elif unresolved_hard_gates or any(
            high_risk_blocks(risk)
            for risk in risks
        ):
            readiness = "critical_attention"
            message = (
                "Potential hard gates or high-severity risks remain unresolved. "
                "Do not treat the opportunity as bid-ready yet."
            )
        elif (
            needs_evidence_count
            or unresolved_explicit
            or package.package_status == "not_ingested"
            or package_intelligence.coverage != "substantive"
            or qualification.evidence_coverage == "none"
        ):
            readiness = "hold_for_evidence"
            message = (
                "The opportunity needs additional evidence or document review before "
                "a confident bid/no-bid decision."
            )
        else:
            readiness = "ready_for_bid_review"
            message = (
                "No unresolved automated blockers remain in the available evidence. "
                "Proceed to human bid review and verify the official source documents."
            )

        actions: list[str] = []
        if package.package_status == "not_ingested":
            actions.append(
                "Ingest the official procurement-document package and refresh this dossier."
            )
        elif package_intelligence.coverage != "substantive":
            actions.append(
                "Review restricted, unsupported, or unread procurement documents manually."
            )
        for hard_gate in unresolved_hard_gates[:3]:
            actions.append(
                "Verify documentary evidence for potential hard gate: "
                f"{hard_gate.label}."
            )
        for explicit_requirement in unresolved_explicit[:3]:
            action = (
                "Review explicit requirement: "
                f"{explicit_requirement.label}."
            )
            if action not in actions:
                actions.append(action)
        if deadline_status == "urgent":
            actions.append(
                "Confirm internal bid capacity against the remaining submission window."
            )
        if strategic_fit == "weak":
            actions.append(
                "Confirm the commercial and strategic rationale for bidding despite weak fit."
            )
        actions.append(
            "Record the final human decision by updating the saved opportunity pipeline stage."
        )

        deduped_actions: list[str] = []
        for action in actions:
            if action not in deduped_actions:
                deduped_actions.append(action)

        return BidNoBidDossier(
            account_id=account_id,
            publication_number=publication_number,
            title=snapshot.title,
            buyer_name=snapshot.buyer_name,
            buyer_country=snapshot.buyer_country,
            source_html_url=snapshot.source_html_url,
            pipeline_stage=opportunity.pipeline_stage or "reviewing",
            pipeline_note=opportunity.note,
            match_score=opportunity.match_score,
            strategic_fit=strategic_fit,
            strategic_fit_reasons=strategic_reasons,
            deadline_readiness=deadline_status,
            days_to_deadline=days_to_deadline,
            notice_review_status=qualification.review_status,
            notice_risk_level=qualification.risk_level,
            document_package_status=package.package_status,
            document_coverage=package_intelligence.coverage,
            checklist=checklist,
            risks=risks,
            evidence_summary=summary,
            review_readiness=readiness,
            review_message=message,
            reviewer_note=review.reviewer_note if review is not None else "",
            next_actions=deduped_actions[:10],
            disclaimer=DOSSIER_DISCLAIMER,
        )

    def update_review(
        self,
        account_id: UUID,
        publication_number: str,
        update: DecisionReviewUpdate,
    ) -> BidNoBidDossier:
        current = self.dossier(account_id, publication_number)
        valid_keys = {item.key for item in current.checklist}
        unknown = sorted(
            item.key
            for item in update.items
            if item.key not in valid_keys
        )
        if unknown:
            raise ValueError(
                "Unknown dossier checklist key(s): " + ", ".join(unknown)
            )

        self._review_repository.upsert(
            account_id,
            publication_number,
            update,
        )
        return self.dossier(account_id, publication_number)
