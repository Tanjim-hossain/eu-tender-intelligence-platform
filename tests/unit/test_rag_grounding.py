from datetime import date

import pytest

from tendergraph.rag.answer import (
    extract_citations,
    validate_grounded_answer,
)
from tendergraph.rag.evidence import (
    TenderEvidence,
)
from tendergraph.rag.prompts import (
    build_user_prompt,
)
from tendergraph.rag.service import (
    GroundedRAGService,
)


def evidence() -> TenderEvidence:
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
        lot_description_text=(
            "Managed cloud platform"
        ),
        buyer_name="Example Buyer",
        buyer_country="BEL",
        cpv_codes=["72000000"],
        procedure_type="open",
        contract_natures=["services"],
        estimated_value=None,
        estimated_value_currency=None,
        earliest_deadline=None,
        latest_deadline=None,
        performance_countries=["BEL"],
        performance_regions=[],
        source_html_url=(
            "https://example.com/tender"
        ),
    )


def test_extract_citations_deduplicates() -> None:
    assert extract_citations(
        "Fact [T1]. More [T1] and [T2]."
    ) == ("T1", "T2")


def test_validate_grounded_answer() -> None:
    answer = validate_grounded_answer(
        "The buyer is Example Buyer [T1].",
        allowed_citations={"T1"},
    )

    assert answer.citations == ("T1",)


def test_rejects_unknown_citation() -> None:
    with pytest.raises(
        ValueError,
        match="unknown citations",
    ):
        validate_grounded_answer(
            "Claim [T9].",
            allowed_citations={"T1"},
        )


def test_rejects_uncited_answer() -> None:
    with pytest.raises(
        ValueError,
        match="at least one citation",
    ):
        validate_grounded_answer(
            "The buyer is Example Buyer.",
            allowed_citations={"T1"},
        )


def test_prompt_deduplicates_description() -> None:
    prompt = build_user_prompt(
        question="What is this tender?",
        evidence=[evidence()],
    )

    assert prompt.count(
        "Managed cloud platform"
    ) == 1


class FakeProvider:
    def generate(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
    ) -> str:
        assert "only from" in system_prompt
        assert "[T1]" in user_prompt

        return (
            "RELEVANT: T1\n"
            "ANSWER:\n"
            "This tender concerns a managed "
            "cloud platform [T1]."
        )


def test_grounded_rag_service() -> None:
    service = GroundedRAGService(
        FakeProvider()
    )

    answer = service.answer(
        question="What is this tender?",
        evidence=[evidence()],
    )

    assert answer.citations == ("T1",)
