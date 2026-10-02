from __future__ import annotations

from datetime import UTC, datetime

from tendergraph.database.config import DatabaseSettings
from tendergraph.database.pool import create_connection_pool
from tendergraph.matching.models import CompanyProfile
from tendergraph.product.models import OpportunitySnapshot, OpportunityStateUpdate
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
        repository = ProductRepository(pool)
        account = repository.create_local_account()

        profile = CompanyProfile(
            company_name="Persistence Smoke Test",
            services=["Data engineering"],
            technologies=["Python"],
            target_countries=["BEL"],
        )
        repository.upsert_profile(
            account.id,
            profile,
        )

        snapshot = OpportunitySnapshot(
            title="Synthetic persistence smoke tender",
            buyer_name="Synthetic Buyer",
            buyer_country="BEL",
            estimated_value=250000,
            estimated_value_currency="EUR",
            earliest_deadline=datetime(
                2026,
                11,
                1,
                tzinfo=UTC,
            ),
            source_html_url=(
                "https://ted.europa.eu/en/notice/-/detail/1-2026"
            ),
        )
        repository.upsert_opportunity(
            account.id,
            "PERSISTENCE-SMOKE-001",
            OpportunityStateUpdate(
                disposition="saved",
                pipeline_stage="qualified",
                note="Verify persistence round trip",
                match_score=91,
                snapshot=snapshot,
            ),
        )

        state = repository.get_state(account.id)
        assert state is not None
        assert state.profile == profile
        assert len(state.opportunities) == 1
        opportunity = state.opportunities[0]
        assert opportunity.publication_number == "PERSISTENCE-SMOKE-001"
        assert opportunity.pipeline_stage == "qualified"
        assert opportunity.snapshot is not None
        assert opportunity.snapshot.title == snapshot.title

        with pool.connection() as connection:
            connection.execute(
                "DELETE FROM product.accounts WHERE id = %(id)s",
                {"id": account.id},
            )
    finally:
        pool.close()


if __name__ == "__main__":
    main()
