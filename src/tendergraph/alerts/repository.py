from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from psycopg_pool import ConnectionPool
from psycopg.types.json import Jsonb

from tendergraph.alerts.models import (
    AlertPreferences,
    AlertPreferencesUpdate,
    TenderAlertItem,
)
from tendergraph.matching.models import TenderMatch


GET_PREFERENCES_SQL = """
SELECT
    enabled,
    min_match_score,
    lookback_days,
    max_items,
    last_refreshed_at
FROM product.alert_preferences
WHERE account_id = %(account_id)s;
"""

UPSERT_PREFERENCES_SQL = """
INSERT INTO product.alert_preferences (
    account_id,
    enabled,
    min_match_score,
    lookback_days,
    max_items
)
VALUES (
    %(account_id)s,
    %(enabled)s,
    %(min_match_score)s,
    %(lookback_days)s,
    %(max_items)s
)
ON CONFLICT (account_id)
DO UPDATE SET
    enabled = EXCLUDED.enabled,
    min_match_score = EXCLUDED.min_match_score,
    lookback_days = EXCLUDED.lookback_days,
    max_items = EXCLUDED.max_items,
    updated_at = CURRENT_TIMESTAMP
RETURNING
    enabled,
    min_match_score,
    lookback_days,
    max_items,
    last_refreshed_at;
"""

TOUCH_REFRESH_SQL = """
INSERT INTO product.alert_preferences (
    account_id,
    last_refreshed_at
)
VALUES (
    %(account_id)s,
    %(refreshed_at)s
)
ON CONFLICT (account_id)
DO UPDATE SET
    last_refreshed_at = EXCLUDED.last_refreshed_at,
    updated_at = CURRENT_TIMESTAMP;
"""

INSERT_EVENT_SQL = """
INSERT INTO product.alert_events (
    account_id,
    publication_number,
    match_score,
    match_payload,
    detected_at
)
VALUES (
    %(account_id)s,
    %(publication_number)s,
    %(match_score)s,
    %(match_payload)s,
    %(detected_at)s
)
ON CONFLICT (account_id, publication_number)
DO NOTHING
RETURNING publication_number;
"""

LIST_EVENTS_SQL = """
SELECT
    match_payload,
    detected_at,
    seen_at
FROM product.alert_events
WHERE
    account_id = %(account_id)s
    AND match_score >= %(min_match_score)s
ORDER BY
    (seen_at IS NULL) DESC,
    match_score DESC,
    detected_at DESC,
    publication_number
LIMIT %(limit)s;
"""

COUNT_EVENTS_SQL = """
SELECT
    COUNT(*) FILTER (WHERE seen_at IS NULL),
    COUNT(*)
FROM product.alert_events
WHERE
    account_id = %(account_id)s
    AND match_score >= %(min_match_score)s;
"""

MARK_SEEN_SQL = """
UPDATE product.alert_events
SET seen_at = COALESCE(seen_at, %(seen_at)s)
WHERE
    account_id = %(account_id)s
    AND publication_number = %(publication_number)s;
"""

MARK_ALL_SEEN_SQL = """
UPDATE product.alert_events
SET seen_at = %(seen_at)s
WHERE
    account_id = %(account_id)s
    AND seen_at IS NULL;
"""

LIST_ENABLED_ACCOUNTS_SQL = """
SELECT preferences.account_id
FROM product.alert_preferences AS preferences
JOIN product.company_profiles AS profiles
  ON profiles.account_id = preferences.account_id
WHERE preferences.enabled = TRUE
ORDER BY preferences.account_id;
"""


def _preferences_from_row(row: tuple[Any, ...]) -> AlertPreferences:
    return AlertPreferences(
        enabled=row[0],
        min_match_score=row[1],
        lookback_days=row[2],
        max_items=row[3],
        last_refreshed_at=row[4],
    )


def _alert_item_from_row(row: tuple[Any, ...]) -> TenderAlertItem:
    match = TenderMatch.model_validate(row[0])
    return TenderAlertItem(
        publication_number=match.publication_number,
        publication_date=match.publication_date,
        title=match.title,
        buyer_name=match.buyer_name,
        buyer_country=match.buyer_country,
        estimated_value=match.estimated_value,
        estimated_value_currency=match.estimated_value_currency,
        earliest_deadline=match.earliest_deadline,
        source_html_url=match.source_html_url,
        match_score=match.match_score,
        why_matches=match.why_matches,
        risks=match.risks,
        detected_at=row[1],
        seen_at=row[2],
    )


class AlertRepository:
    def __init__(self, pool: ConnectionPool) -> None:
        self._pool = pool

    def get_preferences(self, account_id: UUID) -> AlertPreferences:
        with (
            self._pool.connection() as connection,
            connection.cursor() as cursor,
        ):
            cursor.execute(
                GET_PREFERENCES_SQL,
                {"account_id": account_id},
            )
            row = cursor.fetchone()

        if row is None:
            return AlertPreferences()
        return _preferences_from_row(row)

    def upsert_preferences(
        self,
        account_id: UUID,
        preferences: AlertPreferencesUpdate,
    ) -> AlertPreferences:
        with (
            self._pool.connection() as connection,
            connection.cursor() as cursor,
        ):
            cursor.execute(
                UPSERT_PREFERENCES_SQL,
                {
                    "account_id": account_id,
                    **preferences.model_dump(),
                },
            )
            row = cursor.fetchone()

        if row is None:
            raise RuntimeError("Alert preference upsert returned no row")
        return _preferences_from_row(row)

    def touch_refresh(self, account_id: UUID, refreshed_at: datetime) -> None:
        with self._pool.connection() as connection:
            connection.execute(
                TOUCH_REFRESH_SQL,
                {
                    "account_id": account_id,
                    "refreshed_at": refreshed_at,
                },
            )

    def insert_new_events(
        self,
        account_id: UUID,
        matches: list[TenderMatch],
        detected_at: datetime,
    ) -> int:
        inserted = 0
        with (
            self._pool.connection() as connection,
            connection.cursor() as cursor,
        ):
            for match in matches:
                cursor.execute(
                    INSERT_EVENT_SQL,
                    {
                        "account_id": account_id,
                        "publication_number": match.publication_number,
                        "match_score": match.match_score,
                        "match_payload": Jsonb(
                            match.model_dump(mode="json")
                        ),
                        "detected_at": detected_at,
                    },
                )
                if cursor.fetchone() is not None:
                    inserted += 1
        return inserted

    def list_events(
        self,
        account_id: UUID,
        *,
        min_match_score: float,
        limit: int,
    ) -> list[TenderAlertItem]:
        with (
            self._pool.connection() as connection,
            connection.cursor() as cursor,
        ):
            cursor.execute(
                LIST_EVENTS_SQL,
                {
                    "account_id": account_id,
                    "min_match_score": min_match_score,
                    "limit": limit,
                },
            )
            rows = cursor.fetchall()
        return [_alert_item_from_row(row) for row in rows]

    def event_counts(
        self,
        account_id: UUID,
        *,
        min_match_score: float,
    ) -> tuple[int, int]:
        with (
            self._pool.connection() as connection,
            connection.cursor() as cursor,
        ):
            cursor.execute(
                COUNT_EVENTS_SQL,
                {
                    "account_id": account_id,
                    "min_match_score": min_match_score,
                },
            )
            row = cursor.fetchone()
        if row is None:
            return 0, 0
        return int(row[0]), int(row[1])

    def mark_seen(
        self,
        account_id: UUID,
        publication_number: str,
        seen_at: datetime,
    ) -> None:
        with self._pool.connection() as connection:
            connection.execute(
                MARK_SEEN_SQL,
                {
                    "account_id": account_id,
                    "publication_number": publication_number,
                    "seen_at": seen_at,
                },
            )

    def mark_all_seen(self, account_id: UUID, seen_at: datetime) -> None:
        with self._pool.connection() as connection:
            connection.execute(
                MARK_ALL_SEEN_SQL,
                {
                    "account_id": account_id,
                    "seen_at": seen_at,
                },
            )

    def list_enabled_account_ids(self) -> list[UUID]:
        with (
            self._pool.connection() as connection,
            connection.cursor() as cursor,
        ):
            cursor.execute(LIST_ENABLED_ACCOUNTS_SQL)
            rows = cursor.fetchall()
        return [row[0] for row in rows]
