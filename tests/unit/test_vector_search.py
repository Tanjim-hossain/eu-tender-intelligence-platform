import numpy as np
import pytest

from tendergraph.search.vector import (
    VectorIndexMetadata,
    validate_vector_index,
    vector_literal,
)


def test_vector_literal() -> None:
    vector = np.asarray(
        [
            1.0,
            0.5,
            -0.25,
        ],
        dtype=np.float32,
    )

    result = vector_literal(
        vector,
        dimensions=3,
    )

    assert result == "[1,0.5,-0.25]"


def test_vector_literal_rejects_wrong_dimensions() -> None:
    with pytest.raises(
        ValueError,
        match="dimension mismatch",
    ):
        vector_literal(
            np.asarray(
                [1.0, 2.0],
                dtype=np.float32,
            ),
            dimensions=3,
        )


def test_vector_literal_rejects_non_finite() -> None:
    with pytest.raises(
        ValueError,
        match="non-finite",
    ):
        vector_literal(
            np.asarray(
                [
                    1.0,
                    np.nan,
                ],
                dtype=np.float32,
            ),
            dimensions=2,
        )


def test_validate_vector_index() -> None:
    publications = np.asarray(
        [
            "A",
            "B",
        ]
    )

    embeddings = np.zeros(
        (
            2,
            384,
        ),
        dtype=np.float32,
    )

    metadata = VectorIndexMetadata(
        model_name="example/model",
        ingestion_run_id="run-1",
        dimensions=384,
        normalized=True,
        rows=2,
    )

    validate_vector_index(
        publications,
        embeddings,
        metadata,
    )


def test_validate_vector_index_rejects_duplicates() -> None:
    publications = np.asarray(
        [
            "A",
            "A",
        ]
    )

    embeddings = np.zeros(
        (
            2,
            384,
        ),
        dtype=np.float32,
    )

    metadata = VectorIndexMetadata(
        model_name="example/model",
        ingestion_run_id="run-1",
        dimensions=384,
        normalized=True,
        rows=2,
    )

    with pytest.raises(
        ValueError,
        match="Duplicate",
    ):
        validate_vector_index(
            publications,
            embeddings,
            metadata,
        )
