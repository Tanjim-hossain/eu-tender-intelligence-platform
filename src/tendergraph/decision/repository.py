from __future__ import annotations

from typing import Any
from uuid import UUID

from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool

from tendergraph.decision.models import (
    ChecklistReviewItem,
    DecisionReviewUpdate,
    StoredDecisionReview,
)

GET_REVIEW_SQL = """
SELECT
    account_id,
    publication_number,
    items,
    reviewer_note,
    created_at,
    updated_at
FROM product.opportunity_decision_reviews
WHERE account_id = %(account_id)s
  AND publication_number = %(publication_number)s;
"""

UPSERT_REVIEW_SQL = """
INSERT INTO product.opportunity_decision_reviews (
    account_id,
    publication_number,
    items,
    reviewer_note
) VALUES (
    %(account_id)s,
    %(publication_number)s,
    %(items)s,
    %(reviewer_note)s
)
ON CONFLICT (account_id, publication_number)
DO UPDATE SET
    items = EXCLUDED.items,
    reviewer_note = EXCLUDED.reviewer_note,
    updated_at = CURRENT_TIMESTAMP
RETURNING
    account_id,
    publication_number,
    items,
    reviewer_note,
    created_at,
    updated_at;
"""


def _from_row(row: tuple[Any, ...]) -> StoredDecisionReview:
    return StoredDecisionReview(
        account_id=row[0],
        publication_number=row[1],
        items=[
            ChecklistReviewItem.model_validate(item)
            for item in (row[2] or [])
        ],
        reviewer_note=row[3] or "",
        created_at=row[4],
        updated_at=row[5],
    )


class DecisionReviewRepository:
    def __init__(self, pool: ConnectionPool) -> None:
        self._pool = pool

    def get(
        self,
        account_id: UUID,
        publication_number: str,
    ) -> StoredDecisionReview | None:
        with (
            self._pool.connection() as connection,
            connection.cursor() as cursor,
        ):
            cursor.execute(
                GET_REVIEW_SQL,
                {
                    "account_id": account_id,
                    "publication_number": publication_number,
                },
            )
            row = cursor.fetchone()

        return _from_row(row) if row is not None else None

    def upsert(
        self,
        account_id: UUID,
        publication_number: str,
        update: DecisionReviewUpdate,
    ) -> StoredDecisionReview:
        with (
            self._pool.connection() as connection,
            connection.cursor() as cursor,
        ):
            cursor.execute(
                UPSERT_REVIEW_SQL,
                {
                    "account_id": account_id,
                    "publication_number": publication_number,
                    "items": Jsonb(
                        [
                            item.model_dump(mode="json")
                            for item in update.items
                        ]
                    ),
                    "reviewer_note": update.reviewer_note,
                },
            )
            row = cursor.fetchone()

        if row is None:
            raise RuntimeError("Decision review upsert returned no row")
        return _from_row(row)
