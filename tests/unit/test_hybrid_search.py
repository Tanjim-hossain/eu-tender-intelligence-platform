import pytest

from tendergraph.search.hybrid import (
    reciprocal_rank_fusion,
)


def test_rrf_rewards_cross_system_overlap() -> None:
    hits = reciprocal_rank_fusion(
        lexical=[
            "A",
            "B",
            "D",
        ],
        semantic=[
            "A",
            "C",
            "E",
        ],
        limit=5,
    )

    assert (
        hits[0].publication_number
        == "A"
    )
    assert hits[0].lexical_rank == 1
    assert hits[0].semantic_rank == 1


def test_rrf_preserves_source_ranks() -> None:
    hits = reciprocal_rank_fusion(
        lexical=["A", "B"],
        semantic=["B", "C"],
        limit=3,
    )

    by_id = {
        hit.publication_number: hit
        for hit in hits
    }

    assert by_id["A"].lexical_rank == 1
    assert by_id["A"].semantic_rank is None

    assert by_id["B"].lexical_rank == 2
    assert by_id["B"].semantic_rank == 1

    assert by_id["C"].lexical_rank is None
    assert by_id["C"].semantic_rank == 2


def test_rrf_rejects_invalid_parameters() -> None:
    with pytest.raises(
        ValueError,
        match="rrf_k",
    ):
        reciprocal_rank_fusion(
            ["A"],
            ["B"],
            rrf_k=0,
        )

    with pytest.raises(
        ValueError,
        match="limit",
    ):
        reciprocal_rank_fusion(
            ["A"],
            ["B"],
            limit=0,
        )


def test_rrf_supports_semantic_weighting() -> None:
    hits = reciprocal_rank_fusion(
        lexical=["LEXICAL"],
        semantic=["SEMANTIC"],
        lexical_weight=1.0,
        semantic_weight=1.25,
        limit=2,
    )

    assert (
        hits[0].publication_number
        == "SEMANTIC"
    )


def test_rrf_rejects_invalid_weights() -> None:
    with pytest.raises(
        ValueError,
        match="lexical_weight",
    ):
        reciprocal_rank_fusion(
            ["A"],
            ["B"],
            lexical_weight=0,
        )

    with pytest.raises(
        ValueError,
        match="semantic_weight",
    ):
        reciprocal_rank_fusion(
            ["A"],
            ["B"],
            semantic_weight=0,
        )
