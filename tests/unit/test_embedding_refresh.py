from unittest.mock import Mock, patch

import numpy as np
import pytest

from tendergraph.database.config import (
    DatabaseSettings,
)
from tendergraph.search.embedding_refresh import (
    EmbeddingSource,
    normalize_publication_numbers,
    prepare_embedding_documents,
    refresh_tender_embeddings,
)
from tendergraph.search.vector import (
    VectorLoadSummary,
)


def source(
    publication_number: str,
    *,
    run_id: str = "run-1",
    title: str = "Hospital IT platform",
) -> EmbeddingSource:
    return EmbeddingSource(
        publication_number=publication_number,
        ingestion_run_id=run_id,
        title=title,
        description=(
            "Clinical information system"
        ),
        lot_description_text=None,
        buyer_name="Example Hospital",
        procedure_type="open",
        cpv_codes=["72000000"],
        contract_natures=["services"],
    )


class FakeEncoder:
    def __init__(self) -> None:
        self.sentences: list[str] = []

    def encode(
        self,
        sentences: list[str],
        *,
        batch_size: int,
        normalize_embeddings: bool,
        convert_to_numpy: bool,
    ) -> object:
        self.sentences = sentences

        assert batch_size == 32
        assert normalize_embeddings
        assert convert_to_numpy

        return np.ones(
            (
                len(sentences),
                384,
            ),
            dtype=np.float32,
        )


def test_normalize_publication_numbers() -> None:
    assert normalize_publication_numbers(
        [
            " 100001-2026 ",
            "100002-2026",
        ]
    ) == (
        "100001-2026",
        "100002-2026",
    )


@pytest.mark.parametrize(
    "values",
    [
        ["100001-2026", "100001-2026"],
        ["100001-2026", " "],
    ],
)
def test_normalize_publication_numbers_rejects_bad_input(
    values: list[str],
) -> None:
    with pytest.raises(
        ValueError
    ):
        normalize_publication_numbers(
            values
        )


def test_prepare_documents_preserves_requested_order() -> None:
    sources = [
        source(
            "B",
            title="Second",
        ),
        source(
            "A",
            title="First",
        ),
    ]

    run_id, ordered, documents = (
        prepare_embedding_documents(
            sources,
            ["A", "B"],
        )
    )

    assert run_id == "run-1"

    assert [
        item.publication_number
        for item in ordered
    ] == [
        "A",
        "B",
    ]

    assert "First" in documents[0]
    assert "Second" in documents[1]


def test_prepare_documents_requires_one_run() -> None:
    with pytest.raises(
        RuntimeError,
        match="exactly one ingestion run",
    ):
        prepare_embedding_documents(
            [
                source(
                    "A",
                    run_id="run-1",
                ),
                source(
                    "B",
                    run_id="run-2",
                ),
            ],
            ["A", "B"],
        )


def test_refresh_empty_batch_is_noop() -> None:
    settings = Mock(
        spec=DatabaseSettings
    )

    with patch(
        "tendergraph.search.embedding_refresh."
        "fetch_embedding_sources"
    ) as fetch:
        summary = refresh_tender_embeddings(
            settings,
            [],
        )

    fetch.assert_not_called()

    assert summary.requested_rows == 0
    assert summary.embedded_rows == 0
    assert summary.database_rows is None


def test_refresh_embeds_only_requested_rows() -> None:
    settings = Mock(
        spec=DatabaseSettings
    )

    encoder = FakeEncoder()

    sources = [
        source(
            "B",
            title="Second",
        ),
        source(
            "A",
            title="First",
        ),
    ]

    vector_summary = VectorLoadSummary(
        batch_rows=2,
        inserted_rows=1,
        updated_rows=1,
        database_rows=4886,
    )

    with (
        patch(
            "tendergraph.search."
            "embedding_refresh."
            "fetch_embedding_sources",
            return_value=sources,
        ),
        patch(
            "tendergraph.search."
            "embedding_refresh."
            "load_vector_index",
            return_value=vector_summary,
        ) as loader,
    ):
        summary = refresh_tender_embeddings(
            settings,
            ["A", "B"],
            encoder=encoder,
        )

    assert summary.requested_rows == 2
    assert summary.embedded_rows == 2
    assert summary.inserted_rows == 1
    assert summary.updated_rows == 1
    assert summary.database_rows == 4886
    assert summary.ingestion_run_id == "run-1"

    assert "First" in encoder.sentences[0]
    assert "Second" in encoder.sentences[1]

    call = loader.call_args

    assert list(
        call.kwargs[
            "publication_numbers"
        ]
    ) == [
        "A",
        "B",
    ]

    assert (
        call.kwargs[
            "metadata"
        ].ingestion_run_id
        == "run-1"
    )

    assert call.kwargs[
        "embeddings"
    ].shape == (
        2,
        384,
    )
