import numpy as np
import pytest

from tendergraph.search.semantic import (
    build_document_text,
    rank_embeddings,
)


def test_build_document_text() -> None:
    row = {
        "title": "Hospital IT platform",
        "description": (
            "Implementation of a clinical "
            "information system"
        ),
        "lot_description_text": None,
        "buyer_name": "Example Hospital",
        "procedure_type": "open",
        "cpv_codes": [
            "72000000",
        ],
        "contract_natures": [
            "services",
        ],
    }

    text = build_document_text(
        row
    )

    assert text.startswith(
        "passage: "
    )

    assert (
        "Hospital IT platform"
        in text
    )

    assert (
        "clinical information system"
        in text
    )


def test_rank_embeddings_orders_by_similarity() -> None:
    publication_numbers = np.asarray(
        [
            "A",
            "B",
            "C",
        ]
    )

    embeddings = np.asarray(
        [
            [1.0, 0.0],
            [0.8, 0.2],
            [0.0, 1.0],
        ],
        dtype=np.float32,
    )

    query = np.asarray(
        [1.0, 0.0],
        dtype=np.float32,
    )

    hits = rank_embeddings(
        publication_numbers,
        embeddings,
        query,
        limit=2,
    )

    assert [
        hit.publication_number
        for hit in hits
    ] == [
        "A",
        "B",
    ]


def test_rank_embeddings_checks_dimensions() -> None:
    with pytest.raises(
        ValueError,
        match="dimension mismatch",
    ):
        rank_embeddings(
            np.asarray(["A"]),
            np.asarray(
                [[1.0, 0.0]],
                dtype=np.float32,
            ),
            np.asarray(
                [1.0, 0.0, 0.0],
                dtype=np.float32,
            ),
            limit=1,
        )
