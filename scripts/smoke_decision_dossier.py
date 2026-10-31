from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from tendergraph.database.config import DatabaseSettings
from tendergraph.database.pool import create_connection_pool
from tendergraph.decision.models import (
    ChecklistReviewItem,
    DecisionReviewUpdate,
)
from tendergraph.decision.repository import DecisionReviewRepository
from tendergraph.matching.models import CompanyProfile
from tendergraph.product.models import (
    OpportunitySnapshot,
    OpportunityStateUpdate,
)
from tendergraph.product.repository import ProductRepository
from tendergraph.product.schema import ensure_product_schema


def main() -> None:
    settings = DatabaseSettings()
    pool = create_connection_pool(
        settings,
        min_size=1,
        max_size=2,
    )
    pool.open(wait=True)

    try:
        ensure_product_schema(pool)
        product_repository = ProductRepository(pool)
        review_repository = DecisionReviewRepository(pool)

        account = product_repository.create_local_account()
        product_repository.upsert_profile(
            account.id,
            CompanyProfile(
                company_name="Decision Dossier Smoke",
                services=["Data engineering"],
                technologies=["Python"],
                target_countries=["BEL"],
            ),
        )
        product_repository.upsert_opportunity(
            account.id,
            "DECISION-SMOKE-001",
            OpportunityStateUpdate(
                disposition="saved",
                pipeline_stage="reviewing",
                note="Initial pipeline note",
                match_score=87,
                snapshot=OpportunitySnapshot(
                    title="Synthetic decision dossier tender",
                    buyer_name="Synthetic Buyer",
                    buyer_country="BEL",
                    estimated_value=Decimal(300000),
                    estimated_value_currency="EUR",
                    earliest_deadline=datetime(
                        2026,
                        11,
                        30,
                        tzinfo=UTC,
                    ),
                    source_html_url=(
                        "https://ted.europa.eu/en/notice/-/detail/"
                        "DECISION-SMOKE-001"
                    ),
                ),
            ),
        )

        stored = review_repository.upsert(
            account.id,
            "DECISION-SMOKE-001",
            DecisionReviewUpdate(
                items=[
                    ChecklistReviewItem(
                        key="iso_27001",
                        status="verified",
                        note="Certificate checked in bid evidence folder.",
                    ),
                    ChecklistReviewItem(
                        key="similar_contracts",
                        status="needs_evidence",
                        note="Owner to provide three references.",
                    ),
                ],
                reviewer_note="Commercial review pending.",
            ),
        )

        assert stored.account_id == account.id
        assert stored.publication_number == "DECISION-SMOKE-001"
        assert stored.items[0].status == "verified"
        assert stored.items[1].status == "needs_evidence"
        assert stored.reviewer_note == "Commercial review pending."

        round_trip = review_repository.get(
            account.id,
            "DECISION-SMOKE-001",
        )
        assert round_trip is not None
        assert [item.key for item in round_trip.items] == [
            "iso_27001",
            "similar_contracts",
        ]
        assert round_trip.items[0].note.startswith("Certificate checked")

        with pool.connection() as connection:
            connection.execute(
                "DELETE FROM product.accounts WHERE id = %(id)s",
                {"id": account.id},
            )
            row = connection.execute(
                """
                SELECT COUNT(*)
                FROM product.opportunity_decision_reviews
                WHERE account_id = %(id)s
                """,
                {"id": account.id},
            ).fetchone()
            assert row is not None
            assert row[0] == 0
    finally:
        pool.close()


if __name__ == "__main__":
    main()
