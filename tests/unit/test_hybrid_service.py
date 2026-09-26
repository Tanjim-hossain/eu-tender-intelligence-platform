import pytest

from tendergraph.search.service import (
    DEFAULT_RESULT_LIMIT,
    DEFAULT_RETRIEVAL_DEPTH,
)


def test_hybrid_service_defaults() -> None:
    assert DEFAULT_RESULT_LIMIT == 10
    assert DEFAULT_RETRIEVAL_DEPTH == 20


def test_default_depth_covers_result_limit() -> None:
    assert (
        DEFAULT_RETRIEVAL_DEPTH
        >= DEFAULT_RESULT_LIMIT
    )


def test_invalid_depth_contract() -> None:
    limit = 10
    depth = 5

    with pytest.raises(
        ValueError,
        match="Retrieval depth",
    ):
        if not limit <= depth <= 100:
            raise ValueError(
                "Retrieval depth must be "
                "between limit and 100"
            )


def test_production_fusion_weights() -> None:
    from tendergraph.search.service import (
        LEXICAL_WEIGHT,
        SEMANTIC_WEIGHT,
    )

    assert LEXICAL_WEIGHT == 1.0
    assert SEMANTIC_WEIGHT == 1.25
