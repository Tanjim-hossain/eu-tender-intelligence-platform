from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from tendergraph.ingestion.client import TedSearchResult
from tendergraph.ingestion.models import TedSearchRequest


@dataclass(frozen=True, slots=True)
class BronzeArtifact:
    """Files and integrity metadata produced by one Bronze write."""

    data_path: Path
    manifest_path: Path
    sha256: str
    record_count: int


class BronzeWriter:
    """Persist validated TED API responses to the Bronze layer."""

    def __init__(
        self,
        root: str | Path = "data/bronze/ted/search",
    ) -> None:
        self.root = Path(root)

    def write_search_result(
        self,
        *,
        result: TedSearchResult,
        request: TedSearchRequest,
        retrieved_at: datetime | None = None,
    ) -> BronzeArtifact:
        timestamp = retrieved_at or datetime.now(UTC)

        if timestamp.tzinfo is None:
            raise ValueError(
                "retrieved_at must be timezone-aware"
            )

        timestamp = timestamp.astimezone(UTC)

        partition_dir = (
            self.root
            / timestamp.strftime("%Y")
            / timestamp.strftime("%m")
            / timestamp.strftime("%d")
        )
        partition_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        file_stamp = timestamp.strftime(
            "%Y%m%dT%H%M%S%fZ"
        )

        data_path = (
            partition_dir
            / f"ted_search_{file_stamp}.json"
        )

        manifest_path = (
            partition_dir
            / f"ted_search_{file_stamp}.manifest.json"
        )

        data_bytes = self._serialize_json(
            result.raw
        )

        sha256 = hashlib.sha256(
            data_bytes
        ).hexdigest()

        manifest = {
            "schema_version": "1.0",
            "source": "TED Search API v3",
            "retrieved_at_utc": timestamp.isoformat(),
            "request": request.to_api_payload(),
            "total_notice_count": (
                result.parsed.total_notice_count
            ),
            "record_count": len(
                result.parsed.notices
            ),
            "timed_out": result.parsed.timed_out,
            "iteration_next_token": (
                result.parsed.iteration_next_token
            ),
            "data_file": data_path.name,
            "sha256": sha256,
        }

        manifest_bytes = self._serialize_json(
            manifest
        )

        self._atomic_write(
            data_path,
            data_bytes,
        )
        self._atomic_write(
            manifest_path,
            manifest_bytes,
        )

        return BronzeArtifact(
            data_path=data_path,
            manifest_path=manifest_path,
            sha256=sha256,
            record_count=len(
                result.parsed.notices
            ),
        )

    @staticmethod
    def _serialize_json(
        payload: object,
    ) -> bytes:
        text = json.dumps(
            payload,
            indent=2,
            ensure_ascii=False,
            sort_keys=True,
        )

        return f"{text}\n".encode()

    @staticmethod
    def _atomic_write(
        path: Path,
        content: bytes,
    ) -> None:
        temporary_path = path.with_suffix(
            f"{path.suffix}.tmp"
        )

        temporary_path.write_bytes(content)
        temporary_path.replace(path)
