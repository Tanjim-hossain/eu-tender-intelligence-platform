from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from tendergraph.qualification.models import (
    DocumentSignal,
    EvidenceCoverage,
    EvidenceSection,
    QualificationRisk,
    RequirementCategory,
    RequirementSignal,
    RiskSeverity,
    TenderQualification,
)
from tendergraph.rag.evidence import (
    TenderEvidence,
    TenderEvidenceRepository,
)


class TenderNotFoundError(LookupError):
    """Raised when a publication number is not present in Silver."""


@dataclass(frozen=True, slots=True)
class RequirementRule:
    key: str
    category: RequirementCategory
    label: str
    phrases: tuple[str, ...]
    hard_gate: bool = False


@dataclass(frozen=True, slots=True)
class DocumentRule:
    key: str
    label: str
    phrases: tuple[str, ...]


REQUIREMENT_RULES = (
    RequirementRule(
        key="iso_27001",
        category="security",
        label="ISO/IEC 27001 information-security certification",
        phrases=("iso 27001", "iso/iec 27001"),
        hard_gate=True,
    ),
    RequirementRule(
        key="iso_9001",
        category="certification",
        label="ISO 9001 quality-management certification",
        phrases=("iso 9001",),
        hard_gate=True,
    ),
    RequirementRule(
        key="iso_14001",
        category="certification",
        label="ISO 14001 environmental-management certification",
        phrases=("iso 14001",),
        hard_gate=True,
    ),
    RequirementRule(
        key="security_clearance",
        category="security",
        label="Security clearance",
        phrases=(
            "security clearance",
            "habilitation de sécurité",
            "veiligheidsmachtiging",
            "sicherheitsüberprüfung",
            "nulla osta di sicurezza",
        ),
        hard_gate=True,
    ),
    RequirementRule(
        key="annual_turnover",
        category="financial",
        label="Minimum or stated annual turnover",
        phrases=(
            "annual turnover",
            "minimum turnover",
            "chiffre d'affaires",
            "jaaromzet",
            "jahresumsatz",
            "fatturato annuo",
        ),
    ),
    RequirementRule(
        key="professional_liability",
        category="financial",
        label="Professional liability or indemnity insurance",
        phrases=(
            "professional liability insurance",
            "professional indemnity insurance",
            "assurance responsabilité professionnelle",
            "beroepsaansprakelijkheidsverzekering",
            "berufshaftpflichtversicherung",
            "assicurazione responsabilità professionale",
        ),
    ),
    RequirementRule(
        key="similar_experience",
        category="experience",
        label="References or experience on similar contracts",
        phrases=(
            "similar contracts",
            "reference projects",
            "past performance",
            "références similaires",
            "referentieprojecten",
            "vergleichbare aufträge",
            "contratti analoghi",
        ),
    ),
    RequirementRule(
        key="technical_capacity",
        category="technical",
        label="Technical or professional capacity",
        phrases=(
            "technical capacity",
            "technical and professional ability",
            "capacité technique",
            "technische bekwaamheid",
            "technische leistungsfähigkeit",
            "capacità tecnica",
        ),
    ),
    RequirementRule(
        key="named_experts",
        category="staffing",
        label="Named experts, staff qualifications, or CV evidence",
        phrases=(
            "curriculum vitae",
            "staff qualifications",
            "key expert",
            "key experts",
            "personnel qualifications",
            "kwalificaties van personeel",
            "qualifications du personnel",
            "qualifiche del personale",
        ),
    ),
    RequirementRule(
        key="espd",
        category="legal",
        label="European Single Procurement Document or equivalent declaration",
        phrases=(
            "european single procurement document",
            "espd",
            "dume",
            "dg ue",
            "dgue",
            "uniform europees aanbestedingsdocument",
        ),
    ),
    RequirementRule(
        key="tax_social_security",
        category="legal",
        label="Tax or social-security compliance evidence",
        phrases=(
            "tax obligations",
            "social security contributions",
            "tax certificate",
            "attestation fiscale",
            "sociale zekerheidsbijdragen",
            "steuerliche verpflichtungen",
            "obblighi fiscali",
        ),
    ),
)

DOCUMENT_RULES = (
    DocumentRule(
        key="espd_document",
        label="ESPD / procurement self-declaration",
        phrases=(
            "european single procurement document",
            "espd",
            "dume",
            "dgue",
            "uniform europees aanbestedingsdocument",
        ),
    ),
    DocumentRule(
        key="cv_documents",
        label="CVs or curricula vitae",
        phrases=(
            "curriculum vitae",
            "curricula vitae",
            " cvs ",
        ),
    ),
    DocumentRule(
        key="reference_documents",
        label="Reference-project evidence",
        phrases=(
            "reference projects",
            "similar contracts",
            "past performance",
            "références similaires",
            "referentieprojecten",
            "contratti analoghi",
        ),
    ),
    DocumentRule(
        key="certificate_documents",
        label="Certificates or certification evidence",
        phrases=(
            "certificate",
            "certification",
            "certificat",
            "certificaat",
            "zertifikat",
            "certificato",
        ),
    ),
    DocumentRule(
        key="financial_documents",
        label="Financial statements or turnover evidence",
        phrases=(
            "financial statements",
            "annual accounts",
            "annual turnover",
            "chiffre d'affaires",
            "jaarrekening",
            "jahresabschluss",
            "bilancio",
        ),
    ),
    DocumentRule(
        key="insurance_documents",
        label="Insurance evidence",
        phrases=(
            "insurance policy",
            "proof of insurance",
            "professional liability insurance",
            "professional indemnity insurance",
            "beroepsaansprakelijkheidsverzekering",
            "berufshaftpflichtversicherung",
        ),
    ),
)

REQUIREMENT_CUES = (
    "required",
    "must",
    "shall",
    "mandatory",
    "minimum",
    "requis",
    "exigé",
    "obligatoire",
    "doit",
    "verplicht",
    "moet",
    "minimaal",
    "vereist",
    "erforderlich",
    "muss",
    "mindestens",
    "obbligatorio",
    "deve",
    "richiesto",
    "minimo",
)

NEGATION_CUES = (
    "not required",
    "no requirement",
    "not mandatory",
    "pas obligatoire",
    "non requis",
    "niet verplicht",
    "niet vereist",
    "nicht erforderlich",
    "nicht verpflichtend",
    "non obbligatorio",
    "non richiesto",
)

DISCLAIMER = (
    "This review only extracts signals from the indexed TED notice text. "
    "It is not a legal eligibility determination and may omit requirements "
    "contained only in linked procurement documents."
)


def _clean_text(value: str | None) -> str:
    if not value:
        return ""
    return " ".join(value.split())


def _find_phrase(
    text: str,
    phrases: tuple[str, ...],
) -> tuple[int, int] | None:
    folded = text.casefold()
    best: tuple[int, int] | None = None
    for phrase in phrases:
        index = folded.find(phrase.casefold())
        if index < 0:
            continue
        candidate = (index, index + len(phrase))
        if best is None or candidate[0] < best[0]:
            best = candidate
    return best


def _snippet(
    text: str,
    start: int,
    end: int,
    *,
    radius: int = 120,
) -> str:
    left = max(0, start - radius)
    right = min(len(text), end + radius)
    fragment = " ".join(text[left:right].split())
    if left > 0:
        fragment = f"…{fragment}"
    if right < len(text):
        fragment = f"{fragment}…"
    return fragment


def _is_explicit_requirement(
    text: str,
    start: int,
    end: int,
) -> bool:
    left = max(0, start - 120)
    right = min(len(text), end + 120)
    window = text[left:right].casefold()
    if any(cue in window for cue in NEGATION_CUES):
        return False
    return any(cue in window for cue in REQUIREMENT_CUES)


def _sections(
    evidence: TenderEvidence,
) -> tuple[tuple[EvidenceSection, str], ...]:
    return (
        ("description", _clean_text(evidence.description)),
        (
            "lot_description",
            _clean_text(evidence.lot_description_text),
        ),
    )


def _coverage(
    evidence: TenderEvidence,
) -> EvidenceCoverage:
    length = sum(
        len(text)
        for _, text in _sections(evidence)
    )
    if length == 0:
        return "none"
    if length < 300:
        return "limited"
    return "substantive"


def _requirements(
    evidence: TenderEvidence,
) -> list[RequirementSignal]:
    signals: list[RequirementSignal] = []
    sections = _sections(evidence)

    for rule in REQUIREMENT_RULES:
        for section, text in sections:
            match = _find_phrase(text, rule.phrases)
            if match is None:
                continue
            start, end = match
            explicit = _is_explicit_requirement(
                text,
                start,
                end,
            )
            signals.append(
                RequirementSignal(
                    key=rule.key,
                    category=rule.category,
                    label=rule.label,
                    evidence_strength=(
                        "explicit"
                        if explicit
                        else "mentioned"
                    ),
                    evidence=_snippet(
                        text,
                        start,
                        end,
                    ),
                    source_section=section,
                    hard_gate=(
                        rule.hard_gate
                        and explicit
                    ),
                )
            )
            break

    return signals


def _documents(
    evidence: TenderEvidence,
) -> list[DocumentSignal]:
    signals: list[DocumentSignal] = []
    sections = _sections(evidence)

    for rule in DOCUMENT_RULES:
        for section, text in sections:
            match = _find_phrase(text, rule.phrases)
            if match is None:
                continue
            start, end = match
            signals.append(
                DocumentSignal(
                    key=rule.key,
                    label=rule.label,
                    evidence=_snippet(
                        text,
                        start,
                        end,
                    ),
                    source_section=section,
                )
            )
            break

    return signals


def _deadline_risk(
    deadline: datetime | None,
    *,
    now: datetime,
) -> QualificationRisk | None:
    if deadline is None:
        return QualificationRisk(
            key="deadline_unknown",
            severity="medium",
            message=(
                "No submission deadline is available in the "
                "indexed notice fields; verify the official notice."
            ),
            source_section="deadline",
        )

    days = (
        deadline.astimezone(UTC).date()
        - now.astimezone(UTC).date()
    ).days
    if days < 0:
        return QualificationRisk(
            key="deadline_closed",
            severity="high",
            message=(
                "The indexed submission deadline has passed."
            ),
            evidence=deadline.isoformat(),
            source_section="deadline",
        )
    if days <= 3:
        return QualificationRisk(
            key="deadline_critical",
            severity="high",
            message=(
                f"Only {days} day(s) remain until the indexed deadline."
            ),
            evidence=deadline.isoformat(),
            source_section="deadline",
        )
    if days <= 7:
        return QualificationRisk(
            key="deadline_soon",
            severity="medium",
            message=(
                f"Only {days} day(s) remain until the indexed deadline."
            ),
            evidence=deadline.isoformat(),
            source_section="deadline",
        )
    return None


def _risks(
    evidence: TenderEvidence,
    requirements: list[RequirementSignal],
    coverage: EvidenceCoverage,
    *,
    now: datetime,
) -> list[QualificationRisk]:
    risks: list[QualificationRisk] = []
    deadline = _deadline_risk(
        evidence.earliest_deadline,
        now=now,
    )
    if deadline is not None:
        risks.append(deadline)

    if coverage == "none":
        risks.append(
            QualificationRisk(
                key="no_indexed_requirement_text",
                severity="unknown",
                message=(
                    "No description or lot text is indexed for automated "
                    "requirement review."
                ),
            )
        )
    elif coverage == "limited":
        risks.append(
            QualificationRisk(
                key="limited_indexed_requirement_text",
                severity="medium",
                message=(
                    "Only limited notice text is indexed, so important "
                    "requirements may exist only in linked documents."
                ),
            )
        )

    for requirement in requirements:
        if not requirement.hard_gate:
            continue
        severity: RiskSeverity = (
            "high"
            if requirement.category == "security"
            else "medium"
        )
        risks.append(
            QualificationRisk(
                key=f"hard_gate_{requirement.key}",
                severity=severity,
                message=(
                    f"Explicit potential hard gate detected: "
                    f"{requirement.label}."
                ),
                evidence=requirement.evidence,
                source_section=requirement.source_section,
            )
        )

    return risks


def _risk_level(
    risks: list[QualificationRisk],
    coverage: EvidenceCoverage,
) -> RiskSeverity:
    severities = {risk.severity for risk in risks}
    if "high" in severities:
        return "high"
    if "medium" in severities:
        return "medium"
    if coverage == "none" or "unknown" in severities:
        return "unknown"
    return "low"


def _review_status(
    risk_level: RiskSeverity,
    coverage: EvidenceCoverage,
) -> str:
    if coverage == "none":
        return "insufficient_evidence"
    if risk_level == "high":
        return "critical_attention"
    if risk_level in {"medium", "unknown"}:
        return "attention"
    return "no_flags"


def _next_actions(
    requirements: list[RequirementSignal],
    documents: list[DocumentSignal],
    risks: list[QualificationRisk],
) -> list[str]:
    actions: list[str] = []
    risk_keys = {risk.key for risk in risks}

    if "deadline_closed" in risk_keys:
        actions.append(
            "Verify on TED whether the opportunity is still actionable before further review."
        )
    elif {
        "deadline_critical",
        "deadline_soon",
    } & risk_keys:
        actions.append(
            "Confirm the official submission timetable and internal response capacity immediately."
        )

    for requirement in requirements:
        if requirement.hard_gate:
            actions.append(
                f"Verify company evidence for: {requirement.label}."
            )

    for document in documents[:3]:
        actions.append(
            f"Locate or prepare the referenced evidence: {document.label}."
        )

    if not requirements:
        actions.append(
            "Review the official notice and linked procurement documents for eligibility criteria not present in indexed text."
        )

    actions.append(
        "Open the official TED notice and verify every requirement before a bid/no-bid decision."
    )

    deduplicated: list[str] = []
    for action in actions:
        if action not in deduplicated:
            deduplicated.append(action)
    return deduplicated[:8]


class QualificationService:
    def __init__(
        self,
        repository: TenderEvidenceRepository,
    ) -> None:
        self._repository = repository

    def qualify(
        self,
        publication_number: str,
        *,
        now: datetime | None = None,
    ) -> TenderQualification:
        cleaned = publication_number.strip()
        if not cleaned:
            raise ValueError(
                "publication_number must not be blank"
            )

        try:
            evidence = self._repository.fetch(
                [cleaned]
            )
        except RuntimeError as exc:
            raise TenderNotFoundError(
                cleaned
            ) from exc

        if not evidence:
            raise TenderNotFoundError(cleaned)

        tender = evidence[0]
        current = now or datetime.now(UTC)
        coverage = _coverage(tender)
        requirements = _requirements(tender)
        documents = _documents(tender)
        risks = _risks(
            tender,
            requirements,
            coverage,
            now=current,
        )
        risk_level = _risk_level(
            risks,
            coverage,
        )

        return TenderQualification(
            publication_number=(
                tender.publication_number
            ),
            publication_date=tender.publication_date,
            title=tender.title,
            buyer_name=tender.buyer_name,
            buyer_country=tender.buyer_country,
            procedure_type=tender.procedure_type,
            estimated_value=tender.estimated_value,
            estimated_value_currency=(
                tender.estimated_value_currency
            ),
            earliest_deadline=(
                tender.earliest_deadline
            ),
            source_html_url=tender.source_html_url,
            review_status=_review_status(
                risk_level,
                coverage,
            ),
            risk_level=risk_level,
            evidence_coverage=coverage,
            requirements=requirements,
            document_signals=documents,
            risks=risks,
            next_actions=_next_actions(
                requirements,
                documents,
                risks,
            ),
            disclaimer=DISCLAIMER,
        )
