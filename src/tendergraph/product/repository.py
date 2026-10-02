from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool

from tendergraph.matching.models import CompanyProfile
from tendergraph.product.models import (
    OpportunitySnapshot,
    OpportunityStateUpdate,
    ProductAccount,
    ProductState,
    StoredOpportunityState,
)

CREATE_ACCOUNT_SQL = """
INSERT INTO product.accounts (id, account_type)
VALUES (%(id)s, 'local')
RETURNING
    id,
    account_type,
    email,
    display_name,
    created_at,
    updated_at;
"""

GET_ACCOUNT_SQL = """
SELECT
    id,
    account_type,
    email,
    display_name,
    created_at,
    updated_at
FROM product.accounts
WHERE id = %(account_id)s;
"""

GET_PROFILE_SQL = """
SELECT profile
FROM product.company_profiles
WHERE account_id = %(account_id)s;
"""

UPSERT_PROFILE_SQL = """
INSERT INTO product.company_profiles (
    account_id,
    profile
)
VALUES (
    %(account_id)s,
    %(profile)s
)
ON CONFLICT (account_id)
DO UPDATE SET
    profile = EXCLUDED.profile,
    updated_at = CURRENT_TIMESTAMP;
"""

DELETE_PROFILE_SQL = """
DELETE FROM product.company_profiles
WHERE account_id = %(account_id)s;
"""

LIST_OPPORTUNITIES_SQL = """
SELECT
    publication_number,
    disposition,
    pipeline_stage,
    note,
    match_score,
    snapshot,
    created_at,
    updated_at
FROM product.opportunity_states
WHERE account_id = %(account_id)s
ORDER BY updated_at DESC, publication_number;
"""

UPSERT_OPPORTUNITY_SQL = """
INSERT INTO product.opportunity_states (
    account_id,
    publication_number,
    disposition,
    pipeline_stage,
    note,
    match_score,
    snapshot
)
VALUES (
    %(account_id)s,
    %(publication_number)s,
    %(disposition)s,
    %(pipeline_stage)s,
    %(note)s,
    %(match_score)s,
    %(snapshot)s
)
ON CONFLICT (account_id, publication_number)
DO UPDATE SET
    disposition = EXCLUDED.disposition,
    pipeline_stage = EXCLUDED.pipeline_stage,
    note = EXCLUDED.note,
    match_score = EXCLUDED.match_score,
    snapshot = COALESCE(
        EXCLUDED.snapshot,
        product.opportunity_states.snapshot
    ),
    updated_at = CURRENT_TIMESTAMP
RETURNING
    publication_number,
    disposition,
    pipeline_stage,
    note,
    match_score,
    snapshot,
    created_at,
    updated_at;
"""

DELETE_OPPORTUNITY_SQL = """
DELETE FROM product.opportunity_states
WHERE
    account_id = %(account_id)s
    AND publication_number = %(publication_number)s;
"""


def _account_from_row(row: tuple[Any, ...]) -> ProductAccount:
    return ProductAccount(
        id=row[0],
        account_type=row[1],
        email=row[2],
        display_name=row[3],
        created_at=row[4],
        updated_at=row[5],
    )


def _opportunity_from_row(
    row: tuple[Any, ...],
) -> StoredOpportunityState:
    snapshot = row[5]
    return StoredOpportunityState(
        publication_number=row[0],
        disposition=row[1],
        pipeline_stage=row[2],
        note=row[3],
        match_score=row[4],
        snapshot=(
            OpportunitySnapshot.model_validate(snapshot)
            if snapshot is not None
            else None
        ),
        created_at=row[6],
        updated_at=row[7],
    )


class ProductRepository:
    def __init__(self, pool: ConnectionPool) -> None:
        self._pool = pool

    def create_local_account(self) -> ProductAccount:
        with (
            self._pool.connection() as connection,
            connection.cursor() as cursor,
        ):
            cursor.execute(CREATE_ACCOUNT_SQL, {"id": uuid4()})
            row = cursor.fetchone()

        if row is None:
            raise RuntimeError("Account creation returned no row")

        return _account_from_row(row)

    def get_account(
        self,
        account_id: UUID,
    ) -> ProductAccount | None:
        with (
            self._pool.connection() as connection,
            connection.cursor() as cursor,
        ):
            cursor.execute(
                GET_ACCOUNT_SQL,
                {"account_id": account_id},
            )
            row = cursor.fetchone()

        return (
            _account_from_row(row)
            if row is not None
            else None
        )

    def get_state(
        self,
        account_id: UUID,
    ) -> ProductState | None:
        with (
            self._pool.connection() as connection,
            connection.cursor() as cursor,
        ):
            cursor.execute(
                GET_ACCOUNT_SQL,
                {"account_id": account_id},
            )
            account_row = cursor.fetchone()
            if account_row is None:
                return None

            cursor.execute(
                GET_PROFILE_SQL,
                {"account_id": account_id},
            )
            profile_row = cursor.fetchone()

            cursor.execute(
                LIST_OPPORTUNITIES_SQL,
                {"account_id": account_id},
            )
            opportunity_rows = cursor.fetchall()

        profile = (
            CompanyProfile.model_validate(profile_row[0])
            if profile_row is not None
            else None
        )

        return ProductState(
            account=_account_from_row(account_row),
            profile=profile,
            opportunities=[
                _opportunity_from_row(row)
                for row in opportunity_rows
            ],
        )

    def upsert_profile(
        self,
        account_id: UUID,
        profile: CompanyProfile,
    ) -> CompanyProfile:
        with self._pool.connection() as connection:
            connection.execute(
                UPSERT_PROFILE_SQL,
                {
                    "account_id": account_id,
                    "profile": Jsonb(
                        profile.model_dump(mode="json")
                    ),
                },
            )

        return profile

    def delete_profile(
        self,
        account_id: UUID,
    ) -> None:
        with self._pool.connection() as connection:
            connection.execute(
                DELETE_PROFILE_SQL,
                {"account_id": account_id},
            )

    def upsert_opportunity(
        self,
        account_id: UUID,
        publication_number: str,
        update: OpportunityStateUpdate,
    ) -> StoredOpportunityState:
        stage = update.pipeline_stage
        if update.disposition == "saved" and stage is None:
            stage = "reviewing"

        snapshot = (
            Jsonb(
                update.snapshot.model_dump(mode="json")
            )
            if update.snapshot is not None
            else None
        )

        with (
            self._pool.connection() as connection,
            connection.cursor() as cursor,
        ):
            cursor.execute(
                UPSERT_OPPORTUNITY_SQL,
                {
                    "account_id": account_id,
                    "publication_number": publication_number,
                    "disposition": update.disposition,
                    "pipeline_stage": stage,
                    "note": update.note,
                    "match_score": update.match_score,
                    "snapshot": snapshot,
                },
            )
            row = cursor.fetchone()

        if row is None:
            raise RuntimeError(
                "Opportunity upsert returned no row"
            )

        return _opportunity_from_row(row)

    def delete_opportunity(
        self,
        account_id: UUID,
        publication_number: str,
    ) -> None:
        with self._pool.connection() as connection:
            connection.execute(
                DELETE_OPPORTUNITY_SQL,
                {
                    "account_id": account_id,
                    "publication_number": publication_number,
                },
            )
