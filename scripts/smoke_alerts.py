from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

from tendergraph.alerts.models import AlertPreferencesUpdate
from tendergraph.alerts.repository import AlertRepository
from tendergraph.database.config import DatabaseSettings
from tendergraph.database.pool import create_connection_pool
from tendergraph.matching.models import MatchSignals, TenderMatch
from tendergraph.product.repository import ProductRepository
from tendergraph.product.schema import ensure_product_schema


def main() -> None:
    settings = DatabaseSettings()
    pool = create_connection_pool(settings, min_size=1, max_size=2)
    pool.open(wait=True)

    try:
        ensure_product_schema(pool)
        product_repository = ProductRepository(pool)
        alert_repository = AlertRepository(pool)
        account = product_repository.create_local_account()

        preferences = alert_repository.upsert_preferences(
            account.id,
            AlertPreferencesUpdate(
                enabled=True,
                min_match_score=75,
                lookback_days=14,
                max_items=10,
            ),
        )
        assert preferences.min_match_score == 75

        detected_at = datetime(2026, 10, 3, 12, 0, tzinfo=UTC)
        match = TenderMatch(
            publication_number="ALERT-SMOKE-001",
            publication_date=date(2026, 10, 3),
            title="Synthetic alert smoke tender",
            buyer_name="Synthetic Buyer",
            buyer_country="BEL",
            procedure_type="open",
            estimated_value=Decimal(250000),
            estimated_value_currency="EUR",
            earliest_deadline=datetime(2026, 11, 1, tzinfo=UTC),
            source_html_url=(
                "https://ted.europa.eu/en/notice/-/detail/ALERT-SMOKE-001"
            ),
            match_score=91,
            signals=MatchSignals(
                semantic_fit=0.92,
                country_fit=1,
                value_fit=1,
                deadline_fit=1,
                country_status="matched",
                value_status="within_range",
                deadline_status="open",
                days_to_deadline=29,
            ),
            why_matches=["Strong semantic fit with the company capabilities"],
            risks=[],
            rrf_score=0.03,
            lexical_rank=1,
            semantic_rank=1,
            semantic_score=0.92,
        )

        assert alert_repository.insert_new_events(
            account.id,
            [match],
            detected_at,
        ) == 1
        assert alert_repository.insert_new_events(
            account.id,
            [match],
            detected_at,
        ) == 0

        unread_count, total_count = alert_repository.event_counts(
            account.id,
            min_match_score=75,
        )
        assert unread_count == 1
        assert total_count == 1

        items = alert_repository.list_events(
            account.id,
            min_match_score=75,
            limit=10,
        )
        assert len(items) == 1
        assert items[0].publication_number == "ALERT-SMOKE-001"
        assert items[0].match_score == 91

        alert_repository.mark_seen(
            account.id,
            "ALERT-SMOKE-001",
            detected_at,
        )
        unread_count, total_count = alert_repository.event_counts(
            account.id,
            min_match_score=75,
        )
        assert unread_count == 0
        assert total_count == 1

        alert_repository.touch_refresh(account.id, detected_at)
        refreshed = alert_repository.get_preferences(account.id)
        assert refreshed.last_refreshed_at == detected_at

        with pool.connection() as connection:
            connection.execute(
                "DELETE FROM product.accounts WHERE id = %(id)s",
                {"id": account.id},
            )
    finally:
        pool.close()


if __name__ == "__main__":
    main()
