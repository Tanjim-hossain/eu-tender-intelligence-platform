from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Literal

from tendergraph.database.config import (
    DatabaseSettings,
)
from tendergraph.database.silver_loader import (
    LoadSummary,
    load_silver_tenders,
)
from tendergraph.ingestion.client import TedClient
from tendergraph.ingestion.runner import (
    TedIngestionResult,
    ingest_ted_window,
)
from tendergraph.processing.silver_run import (
    DEFAULT_SILVER_RUN_ROOT,
    SilverRunArtifact,
    build_silver_run_artifact,
)
from tendergraph.search.embedding_refresh import (
    EmbeddingRefreshSummary,
    SentenceEncoder,
    refresh_tender_embeddings,
)
from tendergraph.storage.iteration_run import (
    IterationRunWriter,
)

RefreshStage = Literal[
    "ingestion",
    "silver_build",
    "silver_load",
    "embeddings",
]

StageCallback = Callable[
    [RefreshStage],
    None,
]


@dataclass(frozen=True, slots=True)
class IncrementalRefreshSummary:
    ingestion: TedIngestionResult
    silver_artifact: SilverRunArtifact
    silver_load: LoadSummary
    embeddings: EmbeddingRefreshSummary

    @property
    def run_id(self) -> str:
        return self.ingestion.run_artifact.run_id

    @property
    def changed_publication_numbers(
        self,
    ) -> tuple[str, ...]:
        return (
            self.silver_load
            .changed_publication_numbers
        )

    @property
    def changed_rows(self) -> int:
        return len(
            self.changed_publication_numbers
        )


def run_incremental_refresh(
    *,
    start_date: date,
    end_date: date,
    countries: Sequence[str],
    settings: DatabaseSettings | None = None,
    silver_root: Path = DEFAULT_SILVER_RUN_ROOT,
    client: TedClient | None = None,
    writer: IterationRunWriter | None = None,
    encoder: SentenceEncoder | None = None,
    embedding_batch_size: int = 32,
    on_stage_start: StageCallback | None = None,
) -> IncrementalRefreshSummary:
    """Run TED Bronze -> Silver -> DB -> embeddings."""

    active_settings = (
        settings
        if settings is not None
        else DatabaseSettings()
    )

    if on_stage_start is not None:
        on_stage_start("ingestion")

    ingestion = ingest_ted_window(
        start_date=start_date,
        end_date=end_date,
        countries=countries,
        client=client,
        writer=writer,
    )

    if on_stage_start is not None:
        on_stage_start("silver_build")

    silver_artifact = (
        build_silver_run_artifact(
            ingestion.run_artifact.run_dir,
            root=silver_root,
        )
    )

    if (
        silver_artifact.run_id
        != ingestion.run_artifact.run_id
    ):
        raise RuntimeError(
            "Bronze and Silver ingestion "
            "run IDs do not match"
        )

    if on_stage_start is not None:
        on_stage_start("silver_load")

    silver_load = load_silver_tenders(
        silver_artifact.parquet_path,
        active_settings,
    )

    changed_publication_numbers = (
        silver_load
        .changed_publication_numbers
    )

    if on_stage_start is not None:
        on_stage_start("embeddings")

    if changed_publication_numbers:
        embeddings = (
            refresh_tender_embeddings(
                active_settings,
                changed_publication_numbers,
                batch_size=(
                    embedding_batch_size
                ),
                encoder=encoder,
            )
        )
    else:
        embeddings = (
            EmbeddingRefreshSummary(
                requested_rows=0,
                embedded_rows=0,
                inserted_rows=0,
                updated_rows=0,
                database_rows=None,
                ingestion_run_id=None,
            )
        )

    return IncrementalRefreshSummary(
        ingestion=ingestion,
        silver_artifact=silver_artifact,
        silver_load=silver_load,
        embeddings=embeddings,
    )
