import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

from tendergraph.ingestion.client import (
    TedSearchResult,
)
from tendergraph.ingestion.models import (
    TedSearchRequest,
    TedSearchResponse,
)
from tendergraph.storage.bronze import (
    BronzeWriter,
)


def sample_raw_response() -> dict:
    return {
        "notices": [
            {
                "notice-type": "cn-standard",
                "publication-number": "123456-2026",
                "publication-date": "2026-09-24+02:00",
                "classification-cpv": [
                    "72000000",
                ],
                "buyer-name": {
                    "eng": ["Example Authority"],
                },
                "buyer-country": ["BEL"],
                "notice-title": {
                    "eng": "Example data tender",
                },
                "links": {},
            }
        ],
        "totalNoticeCount": 1,
        "iterationNextToken": None,
        "timedOut": False,
    }


def sample_request() -> TedSearchRequest:
    return TedSearchRequest(
        query="buyer-country = BEL",
        fields=[
            "publication-number",
            "publication-date",
        ],
    )


def test_bronze_writer_creates_data_and_manifest(
    tmp_path: Path,
) -> None:
    raw = sample_raw_response()

    result = TedSearchResult(
        raw=raw,
        parsed=TedSearchResponse.model_validate(
            raw
        ),
    )

    writer = BronzeWriter(
        root=tmp_path / "bronze"
    )

    retrieved_at = datetime(
        2026,
        9,
        24,
        19,
        30,
        tzinfo=UTC,
    )

    artifact = writer.write_search_result(
        result=result,
        request=sample_request(),
        retrieved_at=retrieved_at,
    )

    assert artifact.data_path.exists()
    assert artifact.manifest_path.exists()
    assert artifact.record_count == 1

    stored_data = json.loads(
        artifact.data_path.read_text(
            encoding="utf-8"
        )
    )

    assert stored_data == raw

    manifest = json.loads(
        artifact.manifest_path.read_text(
            encoding="utf-8"
        )
    )

    actual_hash = hashlib.sha256(
        artifact.data_path.read_bytes()
    ).hexdigest()

    assert manifest["sha256"] == actual_hash
    assert artifact.sha256 == actual_hash
    assert manifest["record_count"] == 1
    assert manifest["total_notice_count"] == 1
    assert (
        manifest["request"]["query"]
        == "buyer-country = BEL"
    )


def test_bronze_writer_partitions_by_utc_date(
    tmp_path: Path,
) -> None:
    raw = sample_raw_response()

    result = TedSearchResult(
        raw=raw,
        parsed=TedSearchResponse.model_validate(
            raw
        ),
    )

    writer = BronzeWriter(
        root=tmp_path / "bronze"
    )

    artifact = writer.write_search_result(
        result=result,
        request=sample_request(),
        retrieved_at=datetime(
            2026,
            9,
            24,
            23,
            30,
            tzinfo=UTC,
        ),
    )

    assert "2026/09/24" in str(
        artifact.data_path
    )
