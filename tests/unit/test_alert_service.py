from datetime import UTC, date, datetime
from unittest.mock import Mock
from uuid import UUID

import pytest

from tendergraph.alerts.models import AlertPreferences
from tendergraph.alerts.repository import AlertRepository
from tendergraph.alerts.service import AlertService, MissingCompanyProfileError
from tendergraph.matching.models import (
    CompanyMatchResult,
    CompanyProfile,
    MatchSignals,
    TenderMatch,
)
from tendergraph.matching.service import CompanyMatchingService
from tendergraph.product.models import (
    OpportunitySnapshot,
    ProductAccount,
    ProductState,
    StoredOpportunityState,
)
from tendergraph.product.repository import ProductRepository

ACCOUNT_ID = UUID("11111111-1111-4111-8111-111111111111")
NOW = datetime(2026, 10, 3, 12, 0, tzinfo=UTC)


def _profile() -> CompanyProfile:
    return CompanyProfile(
        company_name="Acme Data",
        services=["Data engineering"],
        technologies=["Python"],
        target_countries=["BEL"],
    )


def _account() -> ProductAccount:
    return ProductAccount(
        id=ACCOUNT_ID,
        account_type="local",
        email=None,
        display_name=None,
        created_at=NOW,
        updated_at=NOW,
    )


def _opportunity(publication_number: str) -> StoredOpportunityState:
    return StoredOpportunityState(
        publication_number=publication_number,
        disposition="saved",
        pipeline_stage="reviewing",
        note="",
        match_score=90,
        snapshot=OpportunitySnapshot(
            title="Known opportunity",
            buyer_name="Buyer",
            buyer_country="BEL",
            source_html_url="https://ted.europa.eu/en/notice/-/detail/known",
        ),
        created_at=NOW,
        updated_at=NOW,
    )


def _match(
    publication_number: str,
    *,
    score: float = 85,
    published: date = date(2026, 10, 2),
    deadline_status: str = "open",
) -> TenderMatch:
    return TenderMatch(
        publication_number=publication_number,
        publication_date=published,
        title=f"Tender {publication_number}",
        buyer_name="Example Buyer",
        buyer_country="BEL",
        procedure_type="open",
        estimated_value=250000,
        estimated_value_currency="EUR",
        earliest_deadline=datetime(2026, 10, 20, tzinfo=UTC),
        source_html_url=(
            f"https://ted.europa.eu/en/notice/-/detail/{publication_number}"
        ),
        match_score=score,
        signals=MatchSignals(
            semantic_fit=0.9,
            country_fit=1,
            value_fit=1,
            deadline_fit=1 if deadline_status == "open" else 0,
            country_status="matched",
            value_status="within_range",
            deadline_status=deadline_status,
            days_to_deadline=17 if deadline_status == "open" else -1,
        ),
        why_matches=["Strong semantic fit with the company capabilities"],
        risks=[],
        rrf_score=0.03,
        lexical_rank=1,
        semantic_rank=1,
        semantic_score=0.9,
    )


def _service(
    *,
    state: ProductState,
    matches: list[TenderMatch],
    preferences: AlertPreferences | None = None,
) -> tuple[AlertService, Mock, Mock]:
    product_repository = Mock(spec=ProductRepository)
    product_repository.get_state.return_value = state
    alert_repository = Mock(spec=AlertRepository)
    alert_repository.get_preferences.return_value = preferences or AlertPreferences()
    alert_repository.list_events.return_value = []
    alert_repository.event_counts.return_value = (0, 0)
    alert_repository.insert_new_events.return_value = 1
    matching_service = Mock(spec=CompanyMatchingService)
    matching_service.match.return_value = CompanyMatchResult(
        profile_name="Acme Data",
        query="data engineering Python",
        count=len(matches),
        matches=matches,
    )
    service = AlertService(
        product_repository=product_repository,
        alert_repository=alert_repository,
        matching_service=matching_service,
        now_provider=lambda: NOW,
    )
    return service, alert_repository, matching_service


def test_refresh_filters_by_recency_score_deadline_and_known_state() -> None:
    state = ProductState(
        account=_account(),
        profile=_profile(),
        opportunities=[_opportunity("KNOWN-1")],
    )
    matches = [
        _match("NEW-1"),
        _match("LOW-1", score=60),
        _match("OLD-1", published=date(2026, 8, 1)),
        _match("CLOSED-1", deadline_status="closed"),
        _match("KNOWN-1"),
    ]
    service, repository, _ = _service(state=state, matches=matches)

    result = service.refresh(ACCOUNT_ID)

    assert result.eligible_count == 1
    assert result.new_count == 1
    inserted = repository.insert_new_events.call_args.args[1]
    assert [item.publication_number for item in inserted] == ["NEW-1"]
    repository.touch_refresh.assert_called_once_with(ACCOUNT_ID, NOW)


def test_disabled_preferences_skip_matching() -> None:
    state = ProductState(account=_account(), profile=_profile(), opportunities=[])
    service, _, matching_service = _service(
        state=state,
        matches=[_match("NEW-1")],
        preferences=AlertPreferences(enabled=False),
    )

    result = service.refresh(ACCOUNT_ID)

    assert result.new_count == 0
    assert result.eligible_count == 0
    matching_service.match.assert_not_called()


def test_missing_profile_is_rejected() -> None:
    state = ProductState(account=_account(), profile=None, opportunities=[])
    service, _, _ = _service(state=state, matches=[])

    with pytest.raises(MissingCompanyProfileError):
        service.get_digest(ACCOUNT_ID)


def test_mark_seen_uses_service_clock() -> None:
    state = ProductState(account=_account(), profile=_profile(), opportunities=[])
    service, repository, _ = _service(state=state, matches=[])

    service.mark_seen(ACCOUNT_ID, "1-2026")

    repository.mark_seen.assert_called_once_with(ACCOUNT_ID, "1-2026", NOW)
