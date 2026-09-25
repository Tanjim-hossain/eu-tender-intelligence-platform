import pytest

from tendergraph.search.evaluation import (
    evaluate_ranking,
)


def test_evaluate_perfect_ranking() -> None:
    retrieved = [
        "A",
        "B",
        "C",
    ]

    relevance = {
        "A": 3,
        "B": 2,
        "C": 1,
    }

    metrics = evaluate_ranking(
        retrieved,
        relevance,
        k=3,
    )

    assert metrics.precision_at_k == 1.0
    assert metrics.recall_at_k == 1.0
    assert metrics.reciprocal_rank == 1.0
    assert metrics.ndcg_at_k == pytest.approx(
        1.0
    )


def test_evaluate_partial_ranking() -> None:
    retrieved = [
        "X",
        "B",
        "Y",
        "A",
    ]

    relevance = {
        "A": 3,
        "B": 1,
    }

    metrics = evaluate_ranking(
        retrieved,
        relevance,
        k=4,
    )

    assert metrics.precision_at_k == 0.5
    assert metrics.recall_at_k == 1.0
    assert metrics.reciprocal_rank == 0.5

    assert 0.0 < metrics.ndcg_at_k < 1.0


def test_evaluate_requires_relevant_items() -> None:
    with pytest.raises(
        ValueError,
        match="relevant item",
    ):
        evaluate_ranking(
            ["A"],
            {},
            k=10,
        )
