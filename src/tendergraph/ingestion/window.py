from __future__ import annotations

import re
from collections.abc import Sequence
from datetime import date

DEFAULT_COUNTRIES: tuple[str, ...] = (
    "BEL",
    "NLD",
    "DEU",
    "ITA",
)

_COUNTRY_CODE_PATTERN = re.compile(
    r"^[A-Z]{3}$"
)


def normalize_country_codes(
    countries: Sequence[str],
) -> tuple[str, ...]:
    normalized = tuple(
        country.strip().upper()
        for country in countries
    )

    if not normalized or any(
        not country
        for country in normalized
    ):
        raise ValueError(
            "At least one country code is required"
        )

    invalid = [
        country
        for country in normalized
        if _COUNTRY_CODE_PATTERN.fullmatch(
            country
        )
        is None
    ]

    if invalid:
        raise ValueError(
            "Country codes must be three-letter "
            f"uppercase codes: {invalid}"
        )

    if len(set(normalized)) != len(
        normalized
    ):
        raise ValueError(
            "Country codes must be unique"
        )

    return normalized


def build_publication_window_query(
    *,
    start_date: date,
    end_date: date,
    countries: Sequence[str] = DEFAULT_COUNTRIES,
) -> str:
    if end_date < start_date:
        raise ValueError(
            "end_date must be on or after "
            "start_date"
        )

    country_codes = normalize_country_codes(
        countries
    )

    return (
        "publication-date = "
        f"({start_date:%Y%m%d} <> "
        f"{end_date:%Y%m%d}) "
        "AND buyer-country IN "
        f"({' '.join(country_codes)})"
    )
