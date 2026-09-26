import numpy as np
import pytest

from tendergraph.search.reranker import (
    rerank_scores,
    reranker_document_text,
)


def test_rerank_scores_orders_descending() -> None:
    hits = rerank_scores(
        ["A", "B", "C"],
        np.asarray(
            [0.2, 0.9, 0.5],
            dtype=np.float32,
        ),
        limit=3,
    )

    assert [
        hit.publication_number
        for hit in hits
    ] == ["B", "C", "A"]


def test_rerank_scores_preserves_source_rank() -> None:
    hits = rerank_scores(
        ["A", "B"],
        np.asarray(
            [0.4, 0.8],
            dtype=np.float32,
        ),
        limit=2,
    )

    assert hits[0].publication_number == "B"
    assert hits[0].source_rank == 2


def test_rerank_scores_rejects_mismatch() -> None:
    with pytest.raises(
        ValueError,
        match="score count",
    ):
        rerank_scores(
            ["A", "B"],
            np.asarray(
                [0.5],
                dtype=np.float32,
            ),
            limit=1,
        )


def test_rerank_scores_rejects_duplicates() -> None:
    with pytest.raises(
        ValueError,
        match="Duplicate",
    ):
        rerank_scores(
            ["A", "A"],
            np.asarray(
                [0.5, 0.4],
                dtype=np.float32,
            ),
            limit=1,
        )


def test_reranker_document_removes_e5_prefix() -> None:
    text = reranker_document_text(
        {
            "title": "Cloud platform",
            "description": "Data services",
        }
    )

    assert not text.startswith(
        "passage: "
    )
    assert "Title: Cloud platform" in text
