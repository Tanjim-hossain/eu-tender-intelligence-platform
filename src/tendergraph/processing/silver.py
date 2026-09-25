from __future__ import annotations

import hashlib
import json
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

import polars as pl
from pydantic import BaseModel

from tendergraph.ingestion.models import (
    TedNotice,
    TedSearchResponse,
)


class SilverTender(BaseModel):
    """Normalized analytical representation of one TED notice."""

    publication_number: str
    publication_date: date
    publication_date_raw: str
    notice_type: str

    title: str | None
    title_language: str | None

    description: str | None
    description_language: str | None

    lot_descriptions: list[str]
    lot_description_language: str | None
    lot_description_text: str | None

    buyer_name: str | None
    buyer_name_language: str | None

    buyer_countries: list[str]
    first_buyer_country: str | None

    cpv_codes: list[str]
    first_cpv_code: str | None

    procedure_type: str | None
    contract_natures: list[str]

    deadlines: list[datetime]
    earliest_deadline: datetime | None
    latest_deadline: datetime | None

    estimated_value: Decimal | None
    estimated_value_currency: str | None

    performance_countries: list[str]
    performance_regions: list[str]

    source_html_url: str | None
    source_xml_url: str | None

    ingestion_run_id: str
    source: str = "TED Search API v3"


def _dedupe(values: list[str]) -> list[str]:
    """Deduplicate strings while preserving source order."""

    return list(
        dict.fromkeys(
            value.strip()
            for value in values
            if value.strip()
        )
    )


def _clean_optional_string(
    value: str | None,
) -> str | None:
    if value is None:
        return None

    cleaned = value.strip()

    return cleaned or None


def _select_text(
    values: dict[str, str],
    *,
    preferred_language: str = "eng",
) -> tuple[str | None, str | None]:
    """Choose a deterministic text value from multilingual data."""

    preferred = values.get(preferred_language)

    if preferred and preferred.strip():
        return preferred.strip(), preferred_language

    for language in sorted(values):
        value = values[language].strip()

        if value:
            return value, language

    return None, None


def _select_list_text(
    values: dict[str, list[str]],
    *,
    preferred_language: str = "eng",
) -> tuple[list[str], str | None]:
    """Choose one deterministic language for multilingual lists."""

    preferred = _dedupe(
        values.get(
            preferred_language,
            [],
        )
    )

    if preferred:
        return preferred, preferred_language

    for language in sorted(values):
        selected = _dedupe(values[language])

        if selected:
            return selected, language

    return [], None


def _select_buyer_name(
    values: dict[str, list[str]],
    *,
    preferred_language: str = "eng",
) -> tuple[str | None, str | None]:
    """Choose one normalized buyer name."""

    preferred = values.get(
        preferred_language,
        [],
    )

    for buyer in preferred:
        if buyer.strip():
            return (
                buyer.strip(),
                preferred_language,
            )

    for language in sorted(values):
        for buyer in values[language]:
            if buyer.strip():
                return buyer.strip(), language

    return None, None


def _select_link(
    links: dict[str, str],
    *,
    preferred_keys: tuple[str, ...],
) -> str | None:
    for key in preferred_keys:
        value = links.get(key)

        if value:
            return value

    for key in sorted(links):
        value = links[key]

        if value:
            return value

    return None


def _parse_deadlines(
    values: list[str],
) -> list[datetime]:
    """Parse TED deadline strings and normalize them to UTC."""

    parsed: list[datetime] = []

    for raw_value in _dedupe(values):
        try:
            value = datetime.fromisoformat(
                raw_value
            )
        except ValueError as exc:
            raise ValueError(
                "Invalid TED deadline: "
                f"{raw_value!r}"
            ) from exc

        if (
            value.tzinfo is None
            or value.utcoffset() is None
        ):
            raise ValueError(
                "TED deadline must include "
                "a timezone offset: "
                f"{raw_value!r}"
            )

        parsed.append(
            value.astimezone(UTC)
        )

    return sorted(set(parsed))


def _parse_estimated_value(
    value: str | None,
) -> Decimal | None:
    """Parse a TED financial value without floating-point loss."""

    cleaned = _clean_optional_string(value)

    if cleaned is None:
        return None

    try:
        return Decimal(cleaned)
    except InvalidOperation as exc:
        raise ValueError(
            "Invalid TED estimated value: "
            f"{value!r}"
        ) from exc


def normalize_notice(
    notice: TedNotice,
    *,
    run_id: str,
) -> SilverTender:
    """Normalize one validated Bronze TED notice."""

    title, title_language = _select_text(
        notice.notice_title
    )

    description, description_language = (
        _select_text(
            notice.description_proc
        )
    )

    lot_descriptions, lot_language = (
        _select_list_text(
            notice.description_lot,
            preferred_language=(
                description_language
                or "eng"
            ),
        )
    )

    lot_description_text = (
        "\n".join(lot_descriptions)
        if lot_descriptions
        else None
    )

    buyer_name, buyer_language = (
        _select_buyer_name(
            notice.buyer_name
        )
    )

    buyer_countries = _dedupe(
        notice.buyer_country
    )

    cpv_codes = _dedupe(
        notice.classification_cpv
    )

    contract_natures = _dedupe(
        notice.contract_nature
    )

    deadlines = _parse_deadlines(
        notice.deadline
    )

    performance_countries = _dedupe(
        notice.place_of_performance_country_proc
    )

    performance_regions = _dedupe(
        notice.place_of_performance_subdiv_proc
    )

    estimated_value = _parse_estimated_value(
        notice.estimated_value_proc
    )

    estimated_value_currency = (
        _clean_optional_string(
            notice.estimated_value_cur_proc
        )
    )

    if estimated_value_currency is not None:
        estimated_value_currency = (
            estimated_value_currency.upper()
        )

    procedure_type = _clean_optional_string(
        notice.procedure_type
    )

    raw_date = notice.publication_date

    if len(raw_date) < 10:
        raise ValueError(
            "Invalid TED publication date: "
            f"{raw_date!r}"
        )

    publication_date = date.fromisoformat(
        raw_date[:10]
    )

    html_links = notice.links.get(
        "html",
        {},
    )

    xml_links = notice.links.get(
        "xml",
        {},
    )

    return SilverTender(
        publication_number=(
            notice.publication_number
        ),
        publication_date=publication_date,
        publication_date_raw=raw_date,
        notice_type=notice.notice_type,
        title=title,
        title_language=title_language,
        description=description,
        description_language=(
            description_language
        ),
        lot_descriptions=lot_descriptions,
        lot_description_language=(
            lot_language
        ),
        lot_description_text=(
            lot_description_text
        ),
        buyer_name=buyer_name,
        buyer_name_language=buyer_language,
        buyer_countries=buyer_countries,
        first_buyer_country=(
            buyer_countries[0]
            if buyer_countries
            else None
        ),
        cpv_codes=cpv_codes,
        first_cpv_code=(
            cpv_codes[0]
            if cpv_codes
            else None
        ),
        procedure_type=procedure_type,
        contract_natures=contract_natures,
        deadlines=deadlines,
        earliest_deadline=(
            deadlines[0]
            if deadlines
            else None
        ),
        latest_deadline=(
            deadlines[-1]
            if deadlines
            else None
        ),
        estimated_value=estimated_value,
        estimated_value_currency=(
            estimated_value_currency
        ),
        performance_countries=(
            performance_countries
        ),
        performance_regions=(
            performance_regions
        ),
        source_html_url=_select_link(
            html_links,
            preferred_keys=("ENG",),
        ),
        source_xml_url=_select_link(
            xml_links,
            preferred_keys=("MUL", "ENG"),
        ),
        ingestion_run_id=run_id,
    )


def _sha256(path: Path) -> str:
    return hashlib.sha256(
        path.read_bytes()
    ).hexdigest()


def build_silver_dataframe(
    run_dir: Path,
) -> pl.DataFrame:
    """Build one Silver dataframe from a completed Bronze run."""

    manifest_path = (
        run_dir / "run_manifest.json"
    )

    manifest = json.loads(
        manifest_path.read_text()
    )

    if manifest["status"] != "completed":
        raise ValueError(
            "Bronze run is not completed"
        )

    run_id = manifest["run_id"]

    rows: list[dict[str, object]] = []

    for page in manifest["pages"]:
        data_path = (
            run_dir / page["data_file"]
        )

        expected_hash = page["sha256"]

        actual_hash = _sha256(data_path)

        if actual_hash != expected_hash:
            raise ValueError(
                "Bronze integrity check failed: "
                f"{data_path}"
            )

        raw = json.loads(
            data_path.read_text()
        )

        response = (
            TedSearchResponse.model_validate(
                raw
            )
        )

        for notice in response.notices:
            silver = normalize_notice(
                notice,
                run_id=run_id,
            )

            rows.append(
                silver.model_dump(
                    mode="python"
                )
            )

    frame = pl.DataFrame(rows)

    if frame.height != manifest["record_count"]:
        raise ValueError(
            "Silver row count does not match "
            "Bronze run record count"
        )

    if (
        frame["publication_number"].n_unique()
        != frame.height
    ):
        raise ValueError(
            "Duplicate publication numbers "
            "found in Silver dataset"
        )

    return frame
