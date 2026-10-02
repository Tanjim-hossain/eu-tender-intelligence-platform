from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest

from tendergraph.matching.models import CompanyProfile
from tendergraph.matching.service import (
    CompanyMatchingService,
    build_profile_query,
)
from tendergraph.search.service import HybridSearchResult


class StubSearchService:
    def __init__(self, results: list[HybridSearchResult]) -> None:
        self.results = results
        self.calls: list[tuple[str, int, int]] = []

    def search(
        self,
        query: str,
        *,
        limit: int,
        retrieval_depth: int,
    ) -> list[HybridSearchResult]:
        self.calls.append((query, limit, retrieval_depth))
        return self.results


def make_candidate(
    *,
    publication_number: str,
    semantic_score: float,
    buyer_country: str,
    estimated_value: Decimal | None,
    currency: str | None,
    deadline: datetime | None,
    rrf_score: float,
) -> HybridSearchResult:
    return HybridSearchResult(
        publication_number=publication_number,
        publication_date=date(2026, 10, 1),
        title=f"Tender {publication_number}",
        buyer_name="Example Buyer",
        buyer_country=buyer_country,
        procedure_type=None,
        estimated_value=estimated_value,
        estimated_value_currency=currency,
        earliest_deadline=deadline,
        source_html_url="https://example.com/tender",
        rrf_score=rrf_score,
        lexical_rank=2,
        semantic_rank=1,
        semantic_score=semantic_score,
    )


def test_company_profile_normalizes_product_inputs() -> None:
    profile = CompanyProfile(
        company_name="  Acme   Data  ",
        description="  Public   sector analytics ",
        services=[" Data engineering ", "data engineering", "AI"],
        technologies=[" Python ", "python", "Azure"],
        target_countries=[" bel ", "DEU", "BEL"],
        preferred_value_currency="eur",
    )

    assert profile.company_name == "Acme Data"
    assert profile.description == "Public sector analytics"
    assert profile.services == ["Data engineering", "AI"]
    assert profile.technologies == ["Python", "Azure"]
    assert profile.target_countries == ["BEL", "DEU"]
    assert profile.preferred_value_currency == "EUR"


def test_company_profile_rejects_blank_required_terms() -> None:
    with pytest.raises(ValueError):
        CompanyProfile(
            company_name="   ",
            services=["data engineering"],
        )

    with pytest.raises(ValueError):
        CompanyProfile(
            company_name="Acme",
            services=["   "],
        )


def test_company_profile_rejects_inverted_value_range() -> None:
    with pytest.raises(ValueError):
        CompanyProfile(
            company_name="Acme",
            services=["data engineering"],
            preferred_min_value=Decimal("500000"),
            preferred_max_value=Decimal("100000"),
        )


def test_profile_query_uses_capabilities_without_duplicate_terms() -> None:
    profile = CompanyProfile(
        company_name="Acme",
        description="Data and AI consultancy",
        services=["Data engineering", "AI"],
        technologies=["Python", "AI"],
        industries=["Healthcare"],
        keywords=["cloud platform"],
    )

    assert build_profile_query(profile) == (
        "Data and AI consultancy Data engineering AI Python "
        "Healthcare cloud platform"
    )


def test_matching_ranks_fit_and_explains_tradeoffs() -> None:
    now = datetime(2026, 10, 2, 12, tzinfo=UTC)
    good = make_candidate(
        publication_number="good",
        semantic_score=0.88,
        buyer_country="BEL",
        estimated_value=Decimal("250000"),
        currency="EUR",
        deadline=now + timedelta(days=20),
        rrf_score=0.03,
    )
    weaker = make_candidate(
        publication_number="weaker",
        semantic_score=0.80,
        buyer_country="DEU",
        estimated_value=Decimal("900000"),
        currency="EUR",
        deadline=now + timedelta(days=2),
        rrf_score=0.04,
    )
    search = StubSearchService([weaker, good])
    service = CompanyMatchingService(
        search,
        now_provider=lambda: now,
    )
    profile = CompanyProfile(
        company_name="Acme Data",
        services=["data engineering", "analytics"],
        technologies=["Python", "Azure"],
        target_countries=["BEL"],
        preferred_min_value=Decimal("50000"),
        preferred_max_value=Decimal("500000"),
        min_days_to_deadline=7,
    )

    result = service.match(
        profile,
        limit=2,
        retrieval_depth=20,
    )

    assert result.count == 2
    assert result.matches[0].publication_number == "good"
    assert result.matches[0].match_score > result.matches[1].match_score
    assert result.matches[0].signals.country_status == "matched"
    assert result.matches[0].signals.value_status == "within_range"
    assert result.matches[0].signals.deadline_status == "open"
    assert any(
        "target market" in reason
        for reason in result.matches[0].why_matches
    )

    assert result.matches[1].signals.country_status == "mismatched"
    assert result.matches[1].signals.value_status == "above_range"
    assert result.matches[1].signals.deadline_status == "soon"
    assert any(
        "outside the target markets" in risk
        for risk in result.matches[1].risks
    )
    assert search.calls == [
        (result.query, 20, 20)
    ]


def test_matching_marks_expired_tender_as_closed() -> None:
    now = datetime(2026, 10, 2, 12, tzinfo=UTC)
    expired = make_candidate(
        publication_number="expired",
        semantic_score=0.92,
        buyer_country="BEL",
        estimated_value=None,
        currency=None,
        deadline=now - timedelta(hours=1),
        rrf_score=0.05,
    )
    service = CompanyMatchingService(
        StubSearchService([expired]),
        now_provider=lambda: now,
    )
    profile = CompanyProfile(
        company_name="Acme",
        services=["data engineering"],
    )

    result = service.match(profile)

    match = result.matches[0]
    assert match.signals.deadline_status == "closed"
    assert match.signals.deadline_fit == 0
    assert "Tender deadline has passed" in match.risks
