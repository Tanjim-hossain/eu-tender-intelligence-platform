from datetime import date
from decimal import Decimal

import pytest

from tendergraph.rag.context import (
    build_evidence_context,
    format_evidence,
)
from tendergraph.rag.evidence import (
    TenderEvidence,
)


def make_evidence() -> TenderEvidence:
    return TenderEvidence(
        citation_id="T1",
        publication_number="123-2026",
        publication_date=date(
            2026,
            9,
            25,
        ),
        title="Cloud services",
        description="Managed cloud platform",
        lot_description_text=None,
        buyer_name="Example Buyer",
        buyer_country="BEL",
        cpv_codes=["72000000"],
        procedure_type="open",
        contract_natures=["services"],
        estimated_value=Decimal(
            "100000.00"
        ),
        estimated_value_currency="EUR",
        earliest_deadline=None,
        latest_deadline=None,
        performance_countries=["BEL"],
        performance_regions=[],
        source_html_url=(
            "https://example.com/tender"
        ),
    )


def test_format_evidence_contains_citation() -> None:
    text = format_evidence(
        make_evidence()
    )

    assert "[T1]" in text
    assert "123-2026" in text
    assert "Cloud services" in text
    assert "100000.00 EUR" in text


def test_context_preserves_evidence_order() -> None:
    first = make_evidence()

    second = TenderEvidence(
        citation_id="T2",
        publication_number="456-2026",
        publication_date=first.publication_date,
        title=first.title,
        description=first.description,
        lot_description_text=(
            first.lot_description_text
        ),
        buyer_name=first.buyer_name,
        buyer_country=first.buyer_country,
        cpv_codes=first.cpv_codes,
        procedure_type=first.procedure_type,
        contract_natures=(
            first.contract_natures
        ),
        estimated_value=(
            first.estimated_value
        ),
        estimated_value_currency=(
            first.estimated_value_currency
        ),
        earliest_deadline=(
            first.earliest_deadline
        ),
        latest_deadline=(
            first.latest_deadline
        ),
        performance_countries=(
            first.performance_countries
        ),
        performance_regions=(
            first.performance_regions
        ),
        source_html_url=(
            first.source_html_url
        ),
    )

    text = build_evidence_context(
        [first, second]
    )

    assert text.index("[T1]") < (
        text.index("[T2]")
    )


def test_context_requires_evidence() -> None:
    with pytest.raises(
        ValueError,
        match="At least one",
    ):
        build_evidence_context([])
