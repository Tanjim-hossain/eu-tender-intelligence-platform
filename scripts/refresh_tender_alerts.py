from __future__ import annotations

import argparse
import json
from uuid import UUID

from sentence_transformers import SentenceTransformer

from tendergraph.alerts.repository import AlertRepository
from tendergraph.alerts.service import AlertService, MissingCompanyProfileError
from tendergraph.database.config import DatabaseSettings
from tendergraph.database.pool import create_connection_pool
from tendergraph.matching.service import CompanyMatchingService
from tendergraph.product.repository import ProductRepository
from tendergraph.product.schema import ensure_product_schema
from tendergraph.search.semantic import MODEL_NAME
from tendergraph.search.service import HybridSearchService


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Refresh persisted TenderGraph alert digests for enabled product accounts."
        )
    )
    parser.add_argument(
        "--account-id",
        action="append",
        default=[],
        help=(
            "Refresh only this product account UUID. Repeat to refresh multiple accounts. "
            "When omitted, all accounts with enabled alert preferences are refreshed."
        ),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    requested_ids = [UUID(value) for value in args.account_id]
    settings = DatabaseSettings()
    pool = create_connection_pool(settings, min_size=1, max_size=5)
    pool.open(wait=True)

    try:
        ensure_product_schema(pool)
        alert_repository = AlertRepository(pool)
        account_ids = requested_ids or alert_repository.list_enabled_account_ids()
        if not account_ids:
            print(json.dumps({"refreshed_accounts": 0, "results": []}))
            return

        model = SentenceTransformer(MODEL_NAME)
        search_service = HybridSearchService(
            settings,
            pool=pool,
            model=model,
        )
        matching_service = CompanyMatchingService(search_service)
        service = AlertService(
            product_repository=ProductRepository(pool),
            alert_repository=alert_repository,
            matching_service=matching_service,
        )

        results: list[dict[str, object]] = []
        for account_id in account_ids:
            try:
                refresh = service.refresh(account_id)
                results.append(
                    {
                        "account_id": str(account_id),
                        "status": "refreshed",
                        "new_count": refresh.new_count,
                        "eligible_count": refresh.eligible_count,
                        "unread_count": refresh.digest.unread_count,
                    }
                )
            except MissingCompanyProfileError as exc:
                results.append(
                    {
                        "account_id": str(account_id),
                        "status": "skipped",
                        "reason": str(exc),
                    }
                )

        print(
            json.dumps(
                {
                    "refreshed_accounts": sum(
                        item["status"] == "refreshed" for item in results
                    ),
                    "results": results,
                },
                indent=2,
            )
        )
    finally:
        pool.close()


if __name__ == "__main__":
    main()
