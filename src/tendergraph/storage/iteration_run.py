from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, TypedDict

from tendergraph.ingestion.client import TedIterationPage
from tendergraph.ingestion.models import TedSearchRequest
from tendergraph.storage.bronze import (
    BronzeArtifact,
    BronzeWriter,
)


class _PageManifestEntry(TypedDict):
    page_number: int
    record_count: int
    sha256: str
    data_file: str
    manifest_file: str
    next_token_present: bool


@dataclass(frozen=True, slots=True)
class BronzeRunArtifact:
    """Summary of one complete TED iteration run."""

    run_id: str
    run_dir: Path
    manifest_path: Path
    page_count: int
    record_count: int
    status: str


class IterationRunWriter:
    """Persist all pages belonging to one TED ingestion run."""

    def __init__(
        self,
        *,
        root: str | Path = "data/bronze/ted/runs",
        started_at: datetime | None = None,
    ) -> None:
        timestamp = started_at or datetime.now(UTC)

        if timestamp.tzinfo is None:
            raise ValueError(
                "started_at must be timezone-aware"
            )

        self.started_at = timestamp.astimezone(UTC)

        self.run_id = self.started_at.strftime(
            "%Y%m%dT%H%M%S%fZ"
        )

        self.run_dir = (
            Path(root)
            / self.started_at.strftime("%Y")
            / self.started_at.strftime("%m")
            / self.started_at.strftime("%d")
            / self.run_id
        )

        self.run_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        self.page_writer = BronzeWriter(
            root=self.run_dir / "pages"
        )

        self._pages: list[_PageManifestEntry] = []

    def write_page(
        self,
        page: TedIterationPage,
        *,
        retrieved_at: datetime | None = None,
    ) -> BronzeArtifact:
        artifact = self.page_writer.write_search_result(
            result=page.result,
            request=page.request,
            retrieved_at=retrieved_at,
        )

        self._pages.append(
            {
                "page_number": page.page_number,
                "record_count": artifact.record_count,
                "sha256": artifact.sha256,
                "data_file": str(
                    artifact.data_path.relative_to(
                        self.run_dir
                    )
                ),
                "manifest_file": str(
                    artifact.manifest_path.relative_to(
                        self.run_dir
                    )
                ),
                "next_token_present": bool(
                    page.result.parsed
                    .iteration_next_token
                ),
            }
        )

        return artifact

    def finalize(
        self,
        *,
        request: TedSearchRequest,
        total_source_matches: int,
        unique_publication_numbers: int,
        duplicate_publication_numbers: int,
        status: Literal["completed", "failed"],
        finished_at: datetime | None = None,
    ) -> BronzeRunArtifact:
        timestamp = finished_at or datetime.now(UTC)

        if timestamp.tzinfo is None:
            raise ValueError(
                "finished_at must be timezone-aware"
            )

        timestamp = timestamp.astimezone(UTC)

        record_count = sum(
            page["record_count"]
            for page in self._pages
        )

        manifest = {
            "schema_version": "1.0",
            "source": "TED Search API v3",
            "run_id": self.run_id,
            "status": status,
            "started_at_utc": (
                self.started_at.isoformat()
            ),
            "finished_at_utc": (
                timestamp.isoformat()
            ),
            "request": request.to_api_payload(),
            "page_count": len(self._pages),
            "record_count": record_count,
            "total_source_matches": (
                total_source_matches
            ),
            "unique_publication_numbers": (
                unique_publication_numbers
            ),
            "duplicate_publication_numbers": (
                duplicate_publication_numbers
            ),
            "complete_count_match": (
                record_count == total_source_matches
            ),
            "pages": self._pages,
        }

        manifest_path = (
            self.run_dir / "run_manifest.json"
        )

        manifest_path.write_text(
            json.dumps(
                manifest,
                indent=2,
                ensure_ascii=False,
                sort_keys=True,
            )
            + "\n"
        )

        return BronzeRunArtifact(
            run_id=self.run_id,
            run_dir=self.run_dir,
            manifest_path=manifest_path,
            page_count=len(self._pages),
            record_count=record_count,
            status=status,
        )
