from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from tendergraph.search.lexical import (
    LexicalSearchResult,
)


def test_lexical_search_result_preserves_types() -> None:
    result = LexicalSearchResult(
        publication_number="123456-2026",
        publication_date=date(
            2026,
            9,
            24,
        ),
        title="Cloud platform",
        buyer_name="Example Authority",
        buyer_country="BEL",
        procedure_type="open",
        estimated_value=Decimal(
            "129796146.856"
        ),
        estimated_value_currency="EUR",
        earliest_deadline=datetime(
            2026,
            10,
            20,
            10,
            tzinfo=UTC,
        ),
        source_html_url=(
            "https://example.com/tender"
        ),
        rank=0.42,
    )

    assert result.estimated_value == Decimal(
        "129796146.856"
    )

    assert result.earliest_deadline == datetime(
        2026,
        10,
        20,
        10,
        tzinfo=UTC,
    )


def test_search_limit_contract() -> None:
    from tendergraph.search.lexical import (
        search_tenders,
    )

    class DummySettings:
        connection_uri = "unused"

    with pytest.raises(
        ValueError,
        match="between 1 and 100",
    ):
        search_tenders(
            DummySettings(),  # type: ignore[arg-type]
            query="cloud",
            limit=0,
        )


def test_search_rejects_blank_query() -> None:
    from tendergraph.search.lexical import (
        search_tenders,
    )

    class DummySettings:
        connection_uri = "unused"

    with pytest.raises(
        ValueError,
        match="must not be empty",
    ):
        search_tenders(
            DummySettings(),  # type: ignore[arg-type]
            query="   ",
        )
