from datetime import date

import pytest

from tendergraph.ingestion.window import (
    DEFAULT_COUNTRIES,
    build_publication_window_query,
    normalize_country_codes,
)


def test_build_publication_window_query() -> None:
    query = build_publication_window_query(
        start_date=date(2026, 9, 18),
        end_date=date(2026, 9, 24),
        countries=DEFAULT_COUNTRIES,
    )

    assert query == (
        "publication-date = "
        "(20260918 <> 20260924) "
        "AND buyer-country IN "
        "(BEL NLD DEU ITA)"
    )


def test_country_codes_are_normalized() -> None:
    assert normalize_country_codes(
        ["bel", " deu ", "ITA"]
    ) == (
        "BEL",
        "DEU",
        "ITA",
    )


def test_rejects_invalid_date_window() -> None:
    with pytest.raises(
        ValueError,
        match="end_date",
    ):
        build_publication_window_query(
            start_date=date(2026, 9, 25),
            end_date=date(2026, 9, 24),
        )


@pytest.mark.parametrize(
    "countries",
    [
        [],
        ["BE"],
        ["BEL", "BEL"],
        ["B3L"],
    ],
)
def test_rejects_invalid_countries(
    countries: list[str],
) -> None:
    with pytest.raises(ValueError):
        normalize_country_codes(
            countries
        )
