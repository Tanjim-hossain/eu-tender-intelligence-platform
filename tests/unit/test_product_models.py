from datetime import UTC, datetime
from uuid import UUID

import pytest
from pydantic import ValidationError

from tendergraph.product.models import (
    OpportunitySnapshot,
    OpportunityStateUpdate,
    ProductAccount,
)


def _snapshot() -> OpportunitySnapshot:
    return OpportunitySnapshot(
        title="Cloud data platform",
        buyer_name="Example Buyer",
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


def test_saved_opportunity_requires_snapshot() -> None:
    with pytest.raises(ValidationError):
        OpportunityStateUpdate(
            disposition="saved",
        )


def test_ignored_opportunity_rejects_pipeline_stage() -> None:
    with pytest.raises(ValidationError):
        OpportunityStateUpdate(
            disposition="ignored",
            pipeline_stage="qualified",
        )


def test_saved_opportunity_accepts_pipeline_data() -> None:
    update = OpportunityStateUpdate(
        disposition="saved",
        pipeline_stage="qualified",
        note="Strong capability fit",
        match_score=91,
        snapshot=_snapshot(),
    )

    assert update.pipeline_stage == "qualified"
    assert update.snapshot is not None
    assert update.snapshot.buyer_country == "BEL"


def test_product_account_accepts_local_identity() -> None:
    now = datetime(
        2026,
        10,
        2,
        tzinfo=UTC,
    )
    account = ProductAccount(
        id=UUID(
            "11111111-1111-4111-8111-111111111111"
        ),
        account_type="local",
        email=None,
        display_name=None,
        created_at=now,
        updated_at=now,
    )

    assert account.account_type == "local"
